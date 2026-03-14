"""
CreativeOps AI — FastAPI Backend
Autonomous brief-to-proposal agent pipeline for creative agencies.

Endpoints:
  POST /run-agent             — SSE stream, typed events {type, content}  ← Part 2
  POST /pipeline/run          — SSE stream of the full agent pipeline      ← Part 1
  POST /pipeline/run-sync     — Blocking endpoint, returns final JSON (for testing)
  GET  /health                — Health check

The core async generator `run_full_pipeline(brief)` orchestrates:
  1. Research Agent  → streams with "🔍 RESEARCH: " prefix
  2. Proposal Agent  → streams with "✍️ PROPOSAL: " prefix
  3. Critique Agent  → streams with "🔄 CRITIQUE: " prefix
  4. Yields a final JSON blob with the complete outputs

`run_agent_pipeline(brief)` is the Part 2 variant — same three agents but
emits typed SSE events:  {"type": "thinking"|"proposal"|"complete", "content": ...}
The "complete" event includes all mock outputs (folder structure, calendar, email).
"""

import json
import os
import re
from datetime import date
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel

load_dotenv()

from agents.research_agent import run_research_agent
from agents.proposal_agent import run_proposal_agent
from agents.critique_agent import run_critique_agent
from tools.mock_outputs import mock_folder_structure, mock_calendar_blocks, mock_email_preview

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CreativeOps AI",
    description="Autonomous brief-to-proposal agent for creative agencies",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten for production
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


# ---------------------------------------------------------------------------
# Core orchestrator — async generator
# ---------------------------------------------------------------------------

async def run_full_pipeline(brief: str) -> AsyncGenerator[str, None]:
    """
    Async generator that orchestrates the full 3-agent pipeline.

    Yields server-sent event (SSE) formatted strings:
      - Text chunks prefixed by agent name
      - A final "__PIPELINE_COMPLETE__:" sentinel with JSON payload

    Each agent's special sentinel tokens are intercepted here and NOT
    forwarded to the client — they're used internally to pass data between agents.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        yield "data: {\"error\": \"OPENAI_API_KEY not set\"}\n\n"
        return

    openai_client = AsyncOpenAI(api_key=api_key)

    # ------------------------------------------------------------------
    # Stage 1: Research Agent
    # ------------------------------------------------------------------
    yield _sse("🔍 RESEARCH: Starting industry research...\n")

    research_output: dict = {}
    research_buffer = ""

    async for chunk in run_research_agent(brief, client=openai_client):
        if chunk.startswith("__RESEARCH_OUTPUT__:"):
            # Intercept sentinel — parse structured output
            payload = chunk[len("__RESEARCH_OUTPUT__:"):]
            try:
                research_output = json.loads(payload)
            except json.JSONDecodeError:
                research_output = {"_raw": payload}
            # Don't forward sentinel to client
        else:
            yield _sse(f"🔍 RESEARCH: {chunk}")

    yield _sse("\n🔍 RESEARCH: ✅ Research complete.\n\n")

    # ------------------------------------------------------------------
    # Stage 2: Proposal Agent
    # ------------------------------------------------------------------
    yield _sse("✍️ PROPOSAL: Generating project proposal...\n")

    proposal_text = ""

    async for chunk in run_proposal_agent(
        brief=brief,
        research_output=research_output,
        client=openai_client,
    ):
        proposal_text += chunk
        yield _sse(f"✍️ PROPOSAL: {chunk}")

    yield _sse("\n✍️ PROPOSAL: ✅ Proposal draft complete.\n\n")

    # ------------------------------------------------------------------
    # Stage 3: Critique Agent
    # ------------------------------------------------------------------
    yield _sse("🔄 CRITIQUE: Reviewing proposal for quality...\n")

    critique_output: dict = {}

    async for chunk in run_critique_agent(
        proposal_text=proposal_text,
        original_brief=brief,
        client=openai_client,
    ):
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
    yield _sse(
        f"\n🔄 CRITIQUE: ✅ Review complete. "
        f"Score: {score}/10 | Recommendation: {recommendation}\n\n"
    )

    # ------------------------------------------------------------------
    # Final output — complete pipeline result as JSON
    # ------------------------------------------------------------------
    final_proposal = critique_output.get("final_proposal", proposal_text)

    pipeline_result = {
        "brief": brief,
        "research_output": research_output,
        "proposal_text": proposal_text,
        "critique_output": {
            k: v for k, v in critique_output.items() if k != "final_proposal"
        },
        "final_proposal": final_proposal,
        "pipeline_status": "complete",
    }

    yield _sse(f"__PIPELINE_COMPLETE__:{json.dumps(pipeline_result)}\n\n")


def _sse(data: str) -> str:
    """
    Format a plain string as a Server-Sent Event (Part 1 style).
    Multi-line strings are split so each line gets its own 'data:' prefix,
    which is valid per the SSE spec.
    """
    lines = data.split("\n")
    formatted = "\n".join(f"data: {line}" for line in lines)
    return formatted + "\n\n"


def _sse_event(type_: str, content) -> str:
    """
    Format a typed SSE event (Part 2 style).

    Emits a single SSE event whose data is a JSON object:
      {"type": "<type_>", "content": <content>}

    `content` may be a str (for thinking/proposal chunks) or a dict/list
    (for the final "complete" payload). Both are JSON-serialisable.
    """
    event = {"type": type_, "content": content}
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Part 2 helpers: extract metadata from brief / research output
# ---------------------------------------------------------------------------

def _extract_client_name(brief: str, research_output: dict) -> str:
    """
    Best-effort extraction of the client's organisation name.
    Priority: research_output.client_summary → 'we are X' pattern in brief → fallback.
    """
    # 1. From research summary (model usually starts with the client name)
    summary = research_output.get("client_summary", "")
    if summary:
        # "Tartan Audio is an Edinburgh-based..." or "Tartan Audio, an indie label..."
        match = re.match(r"^([A-Z][^\s,\.]{1,30}(?:\s[A-Z][^\s,\.]{1,20}){0,3})", summary)
        if match:
            return match.group(1).strip()

    # 2. From brief: "We are X", "I am X", "our company is X"
    match = re.search(
        r"(?:we are|i am|our (?:company|studio|agency|label|brand) is)\s+([A-Z][^\.,\n]{2,40})",
        brief,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip().rstrip(".,")

    # 3. Any capitalised proper-noun-looking phrase near the start
    match = re.search(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,3})\b", brief[:200])
    if match:
        return match.group(1).strip()

    return "The Client"


def _extract_project_name(brief: str, research_output: dict) -> str:
    """
    Derive a short project slug from the client name + project type.
    Used as the folder/file slug for mock outputs.
    """
    client = _extract_client_name(brief, research_output)

    # Look for project type keywords
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
    """
    Parse a rough week count from the brief or fall back to 4.
    Looks for patterns like '6 weeks', '8-week', 'two months'.
    """
    brief_lower = brief.lower()

    # Numeric: "6 weeks", "8-week"
    match = re.search(r"(\d+)[\s-]?weeks?", brief_lower)
    if match:
        return min(max(int(match.group(1)), 2), 24)

    # Written: "two months", "three months"
    word_map = {
        "one": 4, "two": 8, "three": 12, "four": 16,
        "five": 20, "six": 24, "half": 2,
    }
    for word, wks in word_map.items():
        if f"{word} month" in brief_lower:
            return wks
        if f"{word} week" in brief_lower:
            return min(wks, 24)

    return 4  # sensible default


# ---------------------------------------------------------------------------
# Part 2: typed-SSE orchestrator
# ---------------------------------------------------------------------------

async def run_agent_pipeline(brief: str) -> AsyncGenerator[str, None]:
    """
    Async generator — Part 2 variant of the agent orchestrator.

    Yields SSE events in the format:
      data: {"type": "thinking"|"proposal"|"complete", "content": ...}\n\n

    Differences from run_full_pipeline (Part 1):
      - Uses _sse_event() instead of _sse()
      - "thinking" type covers research + critique narrative
      - "proposal" type covers every proposal token
      - Final "complete" event carries the full payload including mock outputs
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        yield _sse_event("error", {"message": "OPENAI_API_KEY not configured on server."})
        return

    openai_client = AsyncOpenAI(api_key=api_key)

    # ── Stage 1: Research ──────────────────────────────────────────────────
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

    # ── Stage 2: Proposal ──────────────────────────────────────────────────
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

    # ── Stage 3: Critique ──────────────────────────────────────────────────
    yield _sse_event("thinking", "🔄 Reviewing proposal for quality and completeness...\n")

    critique_output: dict = {}
    async for chunk in run_critique_agent(
        proposal_text=proposal_text,
        original_brief=brief,
        client=openai_client,
    ):
        if chunk.startswith("__CRITIQUE_OUTPUT__:"):
            payload = chunk[len("__CRITIQUE_OUTPUT__:"):]
            try:
                critique_output = json.loads(payload)
            except json.JSONDecodeError:
                critique_output = {"_raw": payload}
        else:
            yield _sse_event("thinking", chunk)

    score = critique_output.get("quality_score", "N/A")
    recommendation = critique_output.get("final_recommendation", "unknown")
    yield _sse_event(
        "thinking",
        f"\n✅ Review complete — Score: {score}/10 | Recommendation: {recommendation}\n\n",
    )

    # ── Mock outputs ───────────────────────────────────────────────────────
    yield _sse_event("thinking", "🗂️  Generating project workspace...\n")

    final_proposal = critique_output.get("final_proposal", proposal_text)
    project_name = _extract_project_name(brief, research_output)
    client_name = _extract_client_name(brief, research_output)
    weeks = _estimate_weeks(brief, research_output)

    folder_structure = mock_folder_structure(project_name)
    calendar_blocks = mock_calendar_blocks(
        start_date=date.today().isoformat(),
        weeks=weeks,
    )
    email_preview = mock_email_preview(
        client_name=client_name,
        proposal_summary=final_proposal[:1000],
    )

    yield _sse_event("thinking", "✅ Workspace ready.\n\n")

    # ── Final complete event ───────────────────────────────────────────────
    complete_payload = {
        "brief": brief,
        "research_output": research_output,
        "proposal_text": proposal_text,
        "critique_output": {
            k: v for k, v in critique_output.items() if k != "final_proposal"
        },
        "final_proposal": final_proposal,
        "folder_structure": folder_structure,
        "calendar_blocks": calendar_blocks,
        "email_preview": email_preview,
        "meta": {
            "client_name": client_name,
            "project_name": project_name,
            "estimated_weeks": weeks,
            "pipeline_status": "complete",
        },
    }

    yield _sse_event("complete", complete_payload)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    api_key_set = bool(os.environ.get("OPENAI_API_KEY"))
    return {
        "status": "ok",
        "openai_key_configured": api_key_set,
        "version": "1.0.0",
    }


# ---------------------------------------------------------------------------
# Part 2 route — typed SSE stream
# ---------------------------------------------------------------------------

@app.post("/run-agent")
async def run_agent(request: BriefRequest):
    """
    Stream the full 3-agent pipeline as typed Server-Sent Events.

    Each event is a JSON object:
      data: {"type": "thinking", "content": "<text chunk>"}\n\n
      data: {"type": "proposal", "content": "<proposal token>"}\n\n
      data: {"type": "complete", "content": { ...full payload + mock outputs }}\n\n

    The final "complete" event contains:
      - research_output    — structured research dict
      - proposal_text      — raw proposal markdown
      - critique_output    — quality review dict
      - final_proposal     — revised proposal after critique
      - folder_structure   — mock project folder tree
      - calendar_blocks    — mock milestone calendar events
      - email_preview      — mock client-ready email (NOT sent)
      - meta               — client_name, project_name, estimated_weeks

    Usage:
      const es = new EventSource('/run-agent');  // or use fetch with ReadableStream
      // For POST, use fetch + ReadableStream (EventSource only supports GET)

    curl example:
      curl -N -X POST http://localhost:8000/run-agent \\
           -H "Content-Type: application/json" \\
           -d '{"brief": "We are Tartan Audio..."}'
    """
    brief = request.brief.strip()
    if not brief:
        raise HTTPException(status_code=400, detail="brief cannot be empty.")

    return StreamingResponse(
        run_agent_pipeline(brief),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/pipeline/run")
async def pipeline_run_stream(request: BriefRequest):
    """
    Stream the full agent pipeline as Server-Sent Events.

    Connect with EventSource in the browser or use curl:
      curl -N -X POST http://localhost:8000/pipeline/run \\
           -H "Content-Type: application/json" \\
           -d '{"brief": "..."}'

    Events:
      - Streaming text with agent prefixes (🔍 RESEARCH, ✍️ PROPOSAL, 🔄 CRITIQUE)
      - Final event prefixed __PIPELINE_COMPLETE__: with JSON payload
    """
    brief = request.brief.strip()
    if not brief:
        raise HTTPException(status_code=400, detail="Brief cannot be empty.")

    return StreamingResponse(
        run_full_pipeline(brief),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.post("/pipeline/run-sync", response_model=PipelineResult)
async def pipeline_run_sync(request: BriefRequest):
    """
    Blocking endpoint that runs the full pipeline and returns the final JSON.
    Useful for testing or when SSE is not supported.
    """
    brief = request.brief.strip()
    if not brief:
        raise HTTPException(status_code=400, detail="Brief cannot be empty.")

    final_result: dict = {}

    async for chunk in run_full_pipeline(brief):
        # Strip SSE framing
        lines = chunk.strip().split("\n")
        for line in lines:
            if line.startswith("data: "):
                content = line[6:]  # Strip "data: " prefix
                if content.startswith("__PIPELINE_COMPLETE__:"):
                    payload = content[len("__PIPELINE_COMPLETE__:"):]
                    try:
                        final_result = json.loads(payload)
                    except json.JSONDecodeError:
                        pass

    if not final_result:
        raise HTTPException(
            status_code=500,
            detail="Pipeline did not produce a final result.",
        )

    return PipelineResult(**final_result)


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
