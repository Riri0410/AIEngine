"""
CreativeOps AI — FastAPI Backend
Autonomous brief-to-proposal agent pipeline for creative agencies.
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
from agents.contract_agent import run_contract_agent
from agents.pricing_agent import run_pricing_agent
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class BriefRequest(BaseModel):
    brief: str

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
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        yield "data: {\"error\": \"OPENAI_API_KEY not set\"}\n\n"
        return

    openai_client = AsyncOpenAI(api_key=api_key)

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

    yield _sse("✍️ PROPOSAL: Generating project proposal...\n")
    proposal_text = ""
    async for chunk in run_proposal_agent(brief=brief, research_output=research_output, client=openai_client):
        proposal_text += chunk
        yield _sse(f"✍️ PROPOSAL: {chunk}")
    yield _sse("\n✍️ PROPOSAL: ✅ Proposal draft complete.\n\n")

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


def _sse(data: str) -> str:
    lines = data.split("\n")
    formatted = "\n".join(f"data: {line}" for line in lines)
    return formatted + "\n\n"

def _sse_event(type_: str, content) -> str:
    event = {"type": type_, "content": content}
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

def _extract_client_name(brief: str, research_output: dict) -> str:
    summary = research_output.get("client_summary", "")
    if summary:
        match = re.match(r"^([A-Z][^\s,\.]{1,30}(?:\s[A-Z][^\s,\.]{1,20}){0,3})", summary)
        if match: return match.group(1).strip()
    match = re.search(r"(?:we are|i am|our (?:company|studio|agency|label|brand) is)\s+([A-Z][^\.,\n]{2,40})", brief, re.IGNORECASE)
    if match: return match.group(1).strip().rstrip(".,")
    match = re.search(r"\b([A-Z][a-z]+(?:\s[A-Z][a-z]+){0,3})\b", brief[:200])
    if match: return match.group(1).strip()
    return "The Client"

def _extract_project_name(brief: str, research_output: dict) -> str:
    client = _extract_client_name(brief, research_output)
    type_keywords = [
        ("brand", "Rebrand"), ("campaign", "Campaign"), ("web", "Web Redesign"),
        ("website", "Web Redesign"), ("market", "Marketing Campaign"), ("digital", "Digital Campaign"),
        ("social", "Social Media Campaign"), ("launch", "Launch Campaign"), ("video", "Video Production"),
        ("identity", "Brand Identity"), ("app", "App Design"), ("strategy", "Strategy Project"),
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
    if match: return min(max(int(match.group(1)), 2), 24)
    word_map = {"one": 4, "two": 8, "three": 12, "four": 16, "five": 20, "six": 24, "half": 2}
    for word, wks in word_map.items():
        if f"{word} month" in brief_lower: return wks
        if f"{word} week" in brief_lower: return min(wks, 24)
    return 4 

async def run_agent_pipeline(brief: str) -> AsyncGenerator[str, None]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        yield _sse_event("error", {"message": "OPENAI_API_KEY not configured on server."})
        return

    openai_client = AsyncOpenAI(api_key=api_key)

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

    yield _sse_event("thinking", "✍️ Generating project proposal...\n")
    proposal_text = ""
    async for chunk in run_proposal_agent(brief=brief, research_output=research_output, client=openai_client):
        proposal_text += chunk
        yield _sse_event("proposal", chunk)
    yield _sse_event("thinking", "\n✅ Proposal draft complete.\n\n")

    yield _sse_event("thinking", "🔄 Reviewing proposal for quality and completeness...\n")
    critique_output: dict = {}
    async for chunk in run_critique_agent(proposal_text=proposal_text, original_brief=brief, client=openai_client):
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
    yield _sse_event("thinking", f"\n✅ Review complete — Score: {score}/10 | Recommendation: {recommendation}\n\n")

    yield _sse_event("thinking", "⚖️ Reviewing scope and contract risks...\n")
    contract_output: dict = {}
    async for chunk in run_contract_agent(brief=brief, proposal_text=proposal_text, client=openai_client):
        if chunk.startswith("__CONTRACT_OUTPUT__:"):
            payload = chunk[len("__CONTRACT_OUTPUT__:"):]
            try:
                contract_output = json.loads(payload)
            except json.JSONDecodeError:
                contract_output = {"_raw": payload}
        else:
            yield _sse_event("thinking", chunk)
            
    yield _sse_event("thinking", "💰 Cross-checking pricing and margins...\n")
    pricing_output: dict = {}
    async for chunk in run_pricing_agent(proposal_text=proposal_text, research_output=research_output, client=openai_client):
        if chunk.startswith("__PRICING_OUTPUT__:"):
            payload = chunk[len("__PRICING_OUTPUT__:"):]
            try:
                pricing_output = json.loads(payload)
            except json.JSONDecodeError:
                pricing_output = {"_raw": payload}
        else:
            yield _sse_event("thinking", chunk)

    yield _sse_event("thinking", "🗂️ Generating project workspace...\n")
    final_proposal = critique_output.get("final_proposal", proposal_text)
    project_name = _extract_project_name(brief, research_output)
    client_name = _extract_client_name(brief, research_output)
    weeks = _estimate_weeks(brief, research_output)

    folder_structure = mock_folder_structure(project_name)
    calendar_blocks = mock_calendar_blocks(start_date=date.today().isoformat(), weeks=weeks)
    email_preview = mock_email_preview(client_name=client_name, proposal_summary=final_proposal[:1000])

    yield _sse_event("thinking", "✅ Workspace ready.\n\n")

    approval_summary = {
        "score": score,
        "recommendation": recommendation,
        "margin_health": pricing_output.get("margin_health", "unknown"),
        "risk_score": contract_output.get("risk_score", 5)
    }
    yield _sse_event("approval_required", approval_summary)

    complete_payload = {
        "brief": brief,
        "research_output": research_output,
        "proposal_text": proposal_text,
        "critique_output": {k: v for k, v in critique_output.items() if k != "final_proposal"},
        "contract_output": contract_output,
        "pricing_output": pricing_output,
        "final_proposal": final_proposal,
        "folder_structure": folder_structure,
        "calendar_blocks": calendar_blocks,
        "email_preview": email_preview,
        "meta": {"client_name": client_name, "project_name": project_name, "estimated_weeks": weeks, "pipeline_status": "complete"},
    }
    yield _sse_event("complete", complete_payload)


@app.get("/health")
async def health_check():
    api_key_set = bool(os.environ.get("OPENAI_API_KEY"))
    return {"status": "ok", "openai_key_configured": api_key_set, "version": "1.0.0"}

@app.post("/run-agent")
async def run_agent(request: BriefRequest):
    brief = request.brief.strip()
    if not brief: raise HTTPException(status_code=400, detail="brief cannot be empty.")
    return StreamingResponse(
        run_agent_pipeline(brief),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )

@app.post("/pipeline/run")
async def pipeline_run_stream(request: BriefRequest):
    brief = request.brief.strip()
    if not brief: raise HTTPException(status_code=400, detail="Brief cannot be empty.")
    return StreamingResponse(
        run_full_pipeline(brief),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

@app.post("/pipeline/run-sync", response_model=PipelineResult)
async def pipeline_run_sync(request: BriefRequest):
    brief = request.brief.strip()
    if not brief: raise HTTPException(status_code=400, detail="Brief cannot be empty.")
    final_result: dict = {}
    async for chunk in run_full_pipeline(brief):
        lines = chunk.strip().split("\n")
        for line in lines:
            if line.startswith("data: "):
                content = line[6:]
                if content.startswith("__PIPELINE_COMPLETE__:"):
                    payload = content[len("__PIPELINE_COMPLETE__:"):]
                    try: final_result = json.loads(payload)
                    except json.JSONDecodeError: pass
    if not final_result: raise HTTPException(status_code=500, detail="Pipeline did not produce a final result.")
    return PipelineResult(**final_result)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")