"""
CreativeOps AI — FastAPI Backend
Autonomous brief-to-proposal agent pipeline for creative agencies.

Endpoints:
  POST /run-agent             — SSE stream, typed events {type, content}
  POST /pipeline/run          — SSE stream of the full agent pipeline
  POST /pipeline/run-sync     — Blocking endpoint, returns final JSON (for testing)
  GET  /health                — Health check + feature flags

  GET  /download/{filename}   — Download a generated file (PDF etc.)
  POST /send-email            — Send the proposal email via SMTP
  GET  /calendar/ics          — Download an ICS file for all project milestones
  GET  /calendar/event-link   — Get a Google Calendar deep-link for one event

The core async generator `run_agent_pipeline(brief)` orchestrates:
  1. Research Agent  → real web search (Tavily) or mock fallback
  2. Proposal Agent  → GPT-4o streaming
  3. Critique Agent  → GPT-4o structured review
  4. PDF generation  → concurrent asyncio tasks
  5. Calendar events → enriched with Google Calendar links + ICS
  6. Email preview   → ready to send via /send-email
"""

import json
import os
import re
import sys
from datetime import date
from typing import AsyncGenerator

# Cloudflare Workers compatibility — kept for cf branch
sys.path.append(os.path.dirname(__file__))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

# Load .env for local dev (optional dep)
if os.path.exists(".env"):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

from agents.research_agent import run_research_agent
from agents.proposal_agent import run_proposal_agent
from agents.critique_agent import run_critique_agent
from agents.contract_agent import run_contract_agent
from agents.pricing_agent import run_pricing_agent

# ── Mock outputs (kept, now enriched by real calendar + PDF generators) ──────
from tools.mock_outputs import (
    mock_folder_structure,
    mock_calendar_blocks,
    mock_email_preview,
)

# ── Real integrations ────────────────────────────────────────────────────────
from tools.document_generator import (
    generate_all_documents_async,
    get_download_path,
    get_output_dir,
)
from tools.email_sender import send_email, smtp_configured
from tools.calendar_generator import (
    enrich_events_with_links,
    generate_ics,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CreativeOps AI",
    description="Autonomous brief-to-proposal agent for creative agencies",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class BriefRequest(BaseModel):
    brief: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "brief": (
                    "We are Tartan Audio, an Edinburgh-based independent music label "
                    "focused on folk and traditional Scottish music. We need a full "
                    "brand refresh and digital marketing campaign to launch our new "
                    "streaming platform. Budget: £15,000. Timeline: 6 weeks."
                )
            }
        }
    }


class PipelineResult(BaseModel):
    brief: str
    research_output: dict
    proposal_text: str
    critique_output: dict
    final_proposal: str
    pipeline_status: str


class SendEmailRequest(BaseModel):
    to: str
    subject: str
    body: str
    cc: str = ""
    reply_to: str = ""


# ---------------------------------------------------------------------------
# Brief metadata extraction helpers
# ---------------------------------------------------------------------------

def _extract_client_name(brief: str, research_output: dict) -> str:
    summary = research_output.get("client_summary", "")
    if summary:
        match = re.match(r"^([A-Z][^\s,\.]{1,30}(?:\s[A-Z][^\s,\.]{1,20}){0,3})", summary)
        if match:
            return match.group(1).strip()

    match = re.search(
        r"(?:we are|i am|our (?:company|studio|agency|label|brand) is)\s+([A-Z][^\.,\n]{2,40})",
        brief, re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().rstrip(".,")

    match = re.search(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,3})\b", brief[:200])
    if match:
        return match.group(1).strip()

    return "The Client"


def _extract_project_name(brief: str, research_output: dict) -> str:
    client = _extract_client_name(brief, research_output)
    type_keywords = [
        ("brand", "Rebrand"),
        ("campaign", "Campaign"),
        ("web", "Web Redesign"),
        ("website", "Web Redesign"),
        ("market", "Marketing Campaign"),
        ("digital", "Digital Campaign"),
        ("social", "Social Media Campaign"),
        ("launch", "Launch Campaign"),
        ("video", "Video Production"),
        ("identity", "Brand Identity"),
        ("app", "App Design"),
        ("strategy", "Strategy Project"),
    ]
    brief_lower = brief.lower()
    project_type = "Project"
    for keyword, label in type_keywords:
        if keyword in brief_lower:
            project_type = label
            break
    return f"{client} {project_type}"


def _estimate_weeks(brief: str, research_output: dict) -> int:
    brief_lower = brief.lower()
    match = re.search(r"(\d+)[\s-]?weeks?", brief_lower)
    if match:
        return min(max(int(match.group(1)), 2), 24)
    word_map = {
        "one": 4, "two": 8, "three": 12, "four": 16,
        "five": 20, "six": 24, "half": 2,
    }
    for word, wks in word_map.items():
        if f"{word} month" in brief_lower:
            return wks
        if f"{word} week" in brief_lower:
            return min(wks, 24)
    return 4


# ---------------------------------------------------------------------------
# SSE formatting helpers
# ---------------------------------------------------------------------------

def _sse(data: str) -> str:
    lines = data.split("\n")
    formatted = "\n".join(f"data: {line}" for line in lines)
    return formatted + "\n\n"


def _sse_event(type_: str, content) -> str:
    event = {"type": type_, "content": content}
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Part 1 pipeline — plain SSE stream
# ---------------------------------------------------------------------------

async def run_full_pipeline(brief: str) -> AsyncGenerator[str, None]:
    """Orchestrates the 3-agent pipeline with plain SSE text events."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        yield _sse('{"error": "OPENAI_API_KEY not set"}')
        return

    openai_client = AsyncOpenAI(api_key=api_key)

    # Stage 1: Research
    yield _sse("🔍 RESEARCH: Starting industry research...\n")
    research_output: dict = {}

    async for chunk in run_research_agent(brief, client=openai_client):
        if chunk.startswith("__RESEARCH_OUTPUT__:"):
            payload = chunk[len("__RESEARCH_OUTPUT__:"):]
            try:
                research_output = json.loads(payload)
            except json.JSONDecodeError:
                research_output = {"_raw": payload}
        else:
            yield _sse(f"🔍 RESEARCH: {chunk}")

    yield _sse("\n🔍 RESEARCH: ✅ Research complete.\n\n")

    # Stage 2: Proposal
    yield _sse("✍️ PROPOSAL: Generating project proposal...\n")
    proposal_text = ""

    async for chunk in run_proposal_agent(brief=brief, research_output=research_output, client=openai_client):
        proposal_text += chunk
        yield _sse(f"✍️ PROPOSAL: {chunk}")

    yield _sse("\n✍️ PROPOSAL: ✅ Proposal draft complete.\n\n")

    # Stage 3: Critique
    yield _sse("🔄 CRITIQUE: Reviewing proposal for quality...\n")
    critique_output: dict = {}

    async for chunk in run_critique_agent(proposal_text=proposal_text, original_brief=brief, client=openai_client):
        if chunk.startswith("__CRITIQUE_OUTPUT__:"):
            payload = chunk[len("__CRITIQUE_OUTPUT__:"):]
            try:
                critique_output = json.loads(payload)
            except json.JSONDecodeError:
                critique_output = {"_raw": payload}
        else:
            yield _sse(f"🔄 CRITIQUE: {chunk}")

    score = critique_output.get("quality_score", "N/A")
    recommendation = critique_output.get("final_recommendation", "unknown")
    yield _sse(f"\n🔄 CRITIQUE: ✅ Review complete. Score: {score}/10 | Recommendation: {recommendation}\n\n")

    yield _sse("⚖️ CONTRACT: Reviewing scope and risks...\n")
    contract_output: dict = {}
    async for chunk in run_contract_agent(brief=brief, proposal_text=proposal_text, client=openai_client):
        if chunk.startswith("__CONTRACT_OUTPUT__:"):
            payload = chunk[len("__CONTRACT_OUTPUT__:"):]
            try: contract_output = json.loads(payload)
            except json.JSONDecodeError: contract_output = {"_raw": payload}
        else: yield _sse(f"⚖️ CONTRACT: {chunk}")
        
    yield _sse("💰 PRICING: Checking benchmarks and margins...\n")
    pricing_output: dict = {}
    async for chunk in run_pricing_agent(proposal_text=proposal_text, research_output=research_output, client=openai_client):
        if chunk.startswith("__PRICING_OUTPUT__:"):
            payload = chunk[len("__PRICING_OUTPUT__:"):]
            try: pricing_output = json.loads(payload)
            except json.JSONDecodeError: pricing_output = {"_raw": payload}
        else: yield _sse(f"💰 PRICING: {chunk}")

    final_proposal = critique_output.get("final_proposal", proposal_text)

    pipeline_result = {
        "brief": brief,
        "research_output": research_output,
        "proposal_text": proposal_text,
        "critique_output": {k: v for k, v in critique_output.items() if k != "final_proposal"},
        "contract_output": contract_output,
        "pricing_output": pricing_output,
        "final_proposal": final_proposal,
        "pipeline_status": "complete",
    }

    yield _sse(f"__PIPELINE_COMPLETE__:{json.dumps(pipeline_result)}\n\n")


# ---------------------------------------------------------------------------
# Part 2 pipeline — typed SSE events (used by the main UI)
# ---------------------------------------------------------------------------

async def run_agent_pipeline(brief: str) -> AsyncGenerator[str, None]:
    """
    Full 5-agent pipeline with typed SSE events + real integrations (Maya -> James -> Priya -> Liam -> Zara).

    Event types:
      thinking  — agent narration / progress text
      proposal  — streaming proposal tokens
      complete  — final payload with all outputs + download links
      error     — pipeline error
    """
    try:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            yield _sse_event("error", {"message": "OPENAI_API_KEY not configured on server."})
            return

        openai_client = AsyncOpenAI(api_key=api_key)

        # ── Stage 1: Research ────────────────────────────────────────────────────
        yield _sse_event("thinking", "🔍 Starting industry research...\n")

        research_output: dict = {}
        async for chunk in run_research_agent(brief, client=openai_client):
            if chunk.startswith("__RESEARCH_OUTPUT__:"):
                payload = chunk[len("__RESEARCH_OUTPUT__:"):]
                try:
                    research_output = json.loads(payload)
                except json.JSONDecodeError:
                    research_output = {"_raw": payload}
            else:
                yield _sse_event("thinking", chunk)

        yield _sse_event("thinking", "\n✅ Research complete.\n\n")

        # ── Stage 2: Proposal ────────────────────────────────────────────────────
        yield _sse_event("thinking", "✍️ Generating project proposal...\n")

        proposal_text = ""
        async for chunk in run_proposal_agent(
            brief=brief,
            research_output=research_output,
            client=openai_client,
        ):
            proposal_text += chunk
            yield _sse_event("proposal", chunk)

        yield _sse_event("thinking", "\n✅ Proposal draft complete.\n\n")

        # ── Stage 3: Critique ────────────────────────────────────────────────────
        yield _sse_event("thinking", "🔄 Reviewing proposal for quality and completeness...\n")

        critique_output: dict = {}
        async for chunk in run_critique_agent(
            proposal_text=proposal_text,
            original_brief=brief,
            client=openai_client,
        ):
            if "__CRITIQUE_OUTPUT__:" in chunk:
                payload = chunk.split("__CRITIQUE_OUTPUT__:")[1]
                try:
                    critique_output = json.loads(payload)
                except json.JSONDecodeError:
                    critique_output = {"_raw": payload}
            else:
                yield _sse_event("thinking", chunk)

        score          = critique_output.get("quality_score", "N/A")
        recommendation = critique_output.get("final_recommendation", "unknown")
        yield _sse_event(
            "thinking",
            f"\n✅ Review complete — Score: {score}/10 | Recommendation: {recommendation}\n\n",
        )

        yield _sse_event("thinking", "⚖️ Reviewing scope and contract risks...\n")
        contract_output: dict = {}
        async for chunk in run_contract_agent(brief=brief, proposal_text=proposal_text, client=openai_client):
            if "__CONTRACT_OUTPUT__:" in chunk:
                payload = chunk.split("__CONTRACT_OUTPUT__:")[1]
                try:
                    contract_output = json.loads(payload)
                except json.JSONDecodeError:
                    contract_output = {"_raw": payload}
            else:
                yield _sse_event("thinking", chunk)
                
        yield _sse_event("thinking", "💰 Cross-checking pricing and margins...\n")
        pricing_output: dict = {}
        async for chunk in run_pricing_agent(proposal_text=proposal_text, research_output=research_output, client=openai_client):
            if "__PRICING_OUTPUT__:" in chunk:
                payload = chunk.split("__PRICING_OUTPUT__:")[1]
                try:
                    pricing_output = json.loads(payload)
                except json.JSONDecodeError:
                    pricing_output = {"_raw": payload}
            else:
                yield _sse_event("thinking", chunk)

        yield _sse_event("thinking", "🗂️ Generating project workspace...\n")
        final_proposal = critique_output.get("final_proposal", proposal_text)
        project_name   = _extract_project_name(brief, research_output)
        client_name    = _extract_client_name(brief, research_output)
        weeks          = _estimate_weeks(brief, research_output)

        # ── Generate PDF concurrently while we build other outputs ───────────────
        yield _sse_event("thinking", "📄 Generating PDF documents...\n")

        import asyncio as _asyncio
        docs_task = _asyncio.create_task(
            generate_all_documents_async(final_proposal, project_name, client_name)
        )

        # ── Mock folder structure (kept — no real file system provisioning yet) ──
        # mock_folder_structure is kept as-is; a future real version would
        # create the directory on a cloud storage bucket.
        folder_structure = mock_folder_structure(project_name)

        # ── Real calendar events + Google Calendar links ─────────────────────────
        yield _sse_event("thinking", "📅 Building project calendar...\n")

        # mock_calendar_blocks still generates the event schedule;
        # enrich_events_with_links adds real Google Calendar deep-links to each event.
        calendar_blocks_raw = mock_calendar_blocks(
            start_date=date.today().isoformat(),
            weeks=weeks,
        )
        calendar_blocks = enrich_events_with_links(calendar_blocks_raw)

        # ── Email preview ────────────────────────────────────────────────────────
        email_preview = mock_email_preview(
            client_name=client_name,
            proposal_summary=final_proposal[:1000],
        )

        # ── Wait for PDF tasks to finish ─────────────────────────────────────────
        docs = await docs_task
        proposal_file = docs.get("proposal_file")

        if proposal_file:
            yield _sse_event("thinking", f"✅ PDF ready — {proposal_file}\n\n")
        else:
            yield _sse_event("thinking", "⚠️  PDF generation skipped (fpdf2 not installed).\n\n")

        yield _sse_event("thinking", "✅ Workspace ready.\n\n")

        approval_summary = {
            "score": score,
            "recommendation": recommendation,
            "margin_health": pricing_output.get("margin_health", "unknown"),
            "risk_score": contract_output.get("risk_score", 5)
        }
        yield _sse_event("approval_required", approval_summary)

        # ── Final complete event ─────────────────────────────────────────────────
        complete_payload = {
            "brief":          brief,
            "research_output": research_output,
            "proposal_text":   proposal_text,
            "critique_output": {k: v for k, v in critique_output.items() if k != "final_proposal"},
            "contract_output": contract_output,
            "pricing_output": pricing_output,
            "final_proposal": final_proposal,
            "folder_structure": folder_structure,
            "calendar_blocks":  calendar_blocks,
            "email_preview":    email_preview,
            "documents": {
                "proposal_pdf":  f"/download/{proposal_file}" if proposal_file else None,
                "proposal_file": proposal_file,
            },
            "meta": {
                "client_name":      client_name,
                "project_name":     project_name,
                "estimated_weeks":  weeks,
                "pipeline_status":  "complete",
                "smtp_configured":  smtp_configured(),
            },
        }

        yield _sse_event("complete", complete_payload)

    except Exception as e:
        import traceback
        traceback.print_exc()
        yield _sse_event("error", {"message": f"Pipeline Error: {str(e)}"})


# ---------------------------------------------------------------------------
# Routes — core pipeline
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    from tools.document_generator import _FPDF_AVAILABLE  # noqa: PLC0415
    from tools.email_sender import _AIOSMTP_AVAILABLE     # noqa: PLC0415
    from tools.calendar_generator import _ICAL_AVAILABLE  # noqa: PLC0415

    tavily_key = bool(os.environ.get("TAVILY_API_KEY"))

    return {
        "status": "ok",
        "version": "2.0.0",
        "features": {
            "openai_configured":  bool(os.environ.get("OPENAI_API_KEY")),
            "real_web_search":    tavily_key,
            "real_pdf_generation": _FPDF_AVAILABLE,
            "real_email_sending": _AIOSMTP_AVAILABLE and smtp_configured(),
            "real_calendar_ics":  _ICAL_AVAILABLE,
        },
    }


@app.post("/run-agent")
async def run_agent(request: BriefRequest):
    """Stream the full 3-agent pipeline as typed Server-Sent Events."""
    brief = request.brief.strip()
    if not brief:
        raise HTTPException(status_code=400, detail="brief cannot be empty.")

    return StreamingResponse(
        run_agent_pipeline(brief),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":       "keep-alive",
        },
    )


@app.post("/pipeline/run")
async def pipeline_run_stream(request: BriefRequest):
    """Stream the full agent pipeline as plain Server-Sent Events."""
    brief = request.brief.strip()
    if not brief:
        raise HTTPException(status_code=400, detail="Brief cannot be empty.")

    return StreamingResponse(
        run_full_pipeline(brief),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/pipeline/run-sync", response_model=PipelineResult)
async def pipeline_run_sync(request: BriefRequest):
    """Blocking endpoint — runs the full pipeline and returns the final JSON."""
    brief = request.brief.strip()
    if not brief:
        raise HTTPException(status_code=400, detail="Brief cannot be empty.")

    final_result: dict = {}
    async for chunk in run_full_pipeline(brief):
        for line in chunk.strip().split("\n"):
            if line.startswith("data: "):
                content = line[6:]
                if content.startswith("__PIPELINE_COMPLETE__:"):
                    try:
                        final_result = json.loads(content[len("__PIPELINE_COMPLETE__:"):])
                    except json.JSONDecodeError:
                        pass

    if not final_result:
        raise HTTPException(status_code=500, detail="Pipeline did not produce a final result.")

    return PipelineResult(**final_result)


# ---------------------------------------------------------------------------
# Routes — file downloads
# ---------------------------------------------------------------------------

@app.get("/download/{filename}")
async def download_file(filename: str):
    """
    Serve a generated document (PDF etc.) for download.

    Files are written to the OS temp directory by document_generator.py.
    The filename is returned in the 'complete' SSE event under
    payload.documents.proposal_file.
    """
    # Security: only allow filenames (no path traversal)
    safe_name = os.path.basename(filename)
    filepath = get_download_path(safe_name)

    if filepath is None:
        raise HTTPException(status_code=404, detail=f"File not found: {safe_name}")

    media_type = "application/pdf" if safe_name.endswith(".pdf") else "application/octet-stream"
    return FileResponse(
        path=str(filepath),
        media_type=media_type,
        filename=safe_name,
    )


# ---------------------------------------------------------------------------
# Routes — email
# ---------------------------------------------------------------------------

@app.post("/send-email")
async def send_email_endpoint(request: SendEmailRequest):
    """
    Send the proposal email via SMTP.

    Requires SMTP_HOST, SMTP_USER, SMTP_PASSWORD environment variables.
    Returns {"success": true/false, "message": "..."} or {"error": "..."}.
    """
    if not request.to or "@" not in request.to:
        raise HTTPException(status_code=400, detail="Invalid 'to' email address.")

    result = await send_email(
        to=request.to,
        subject=request.subject,
        body=request.body,
        cc=request.cc,
        reply_to=request.reply_to,
    )

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Email send failed."))

    return result


# ---------------------------------------------------------------------------
# Routes — calendar
# ---------------------------------------------------------------------------

class IcsRequest(BaseModel):
    events: list[dict]
    project_name: str = "Creative Project"


@app.post("/calendar/ics")
async def download_ics(request: IcsRequest):
    """
    Generate and return an ICS calendar file for all project milestones.

    The client passes the `calendar_blocks` array from the complete payload.
    """
    ics_content = generate_ics(
        events=request.events,
        project_name=request.project_name,
    )

    if ics_content is None:
        raise HTTPException(
            status_code=503,
            detail="ICS generation unavailable (icalendar package not installed).",
        )

    slug = re.sub(r"[^\w-]", "_", request.project_name.lower())[:40]
    filename = f"{slug}_schedule.ics"

    return StreamingResponse(
        iter([ics_content]),
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "text/calendar; charset=utf-8",
        },
    )


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
