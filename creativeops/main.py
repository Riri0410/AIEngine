"""
CreativeOps AI — FastAPI Backend
5-agent autonomous pipeline: Maya → James → Priya → Liam → Zara

Agents:
  Maya  — Research Director (market intel, past client recall, Fringe detection)
  James — Account Director (proposal writing, strategy)
  Priya — Creative Director (quality review, revision)
  Liam  — Contract Scout (scope/IP/payment risk analysis)
  Zara  — Pricing Strategist (budget benchmarking, upsell opportunities)

Inter-agent messaging streams live in the terminal — agents pass notes to each other.
After all agents complete, emits approval_required event, then complete event.
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
from tools.mock_outputs import (
    mock_folder_structure,
    mock_calendar_blocks,
    mock_email_preview,
    mock_contract_document,
)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(
    title="CreativeOps AI",
    description="5-agent autonomous creative back office",
    version="2.0.0",
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
    is_fringe: bool = False


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse_event(type_: str, content) -> str:
    event = {"type": type_, "content": content}
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _agent_msg_event(from_agent: str, to_agent: str, message: str) -> str:
    """Live inter-agent message — streams in the terminal as a conversation thread."""
    return _sse_event("agent_message", {"from": from_agent, "to": to_agent, "message": message})


# ---------------------------------------------------------------------------
# Inter-agent messages (context-aware, dynamically generated)
# ---------------------------------------------------------------------------

def _maya_to_james(brief: str, research_output: dict) -> str:
    benchmarks = research_output.get("budget_benchmarks", {})
    mid = benchmarks.get("market_mid") or benchmarks.get("recommended_budget", 0)
    stated = research_output.get("stated_budget", 0)
    competitors = research_output.get("competitors", [])
    is_fringe = research_output.get("is_fringe", False)

    if is_fringe:
        return (
            "Fringe act confirmed. Edinburgh festival economics are brutal — average act spends £8k–22k total, "
            "marketing is 12–18% of that. Our Fringe Forward result (91% sell-through) is the ONLY proof point that "
            "matters to arts clients. Lead with it in your Executive Summary."
        )
    if stated and mid and stated < mid * 0.75:
        gap_pct = int((1 - stated / mid) * 100)
        return (
            f"Their stated budget (£{stated:,}) is {gap_pct}% below market mid (£{mid:,}). "
            f"Anchor deliverables to outcomes, not hours. I'd open at £{int(mid * 0.88):,} and let them negotiate down."
        )
    if stated and mid and stated > mid * 1.2:
        return (
            f"Budget (£{stated:,}) is above market mid (£{mid:,}). Price at full rate and add premium deliverables. Don't discount."
        )
    if competitors:
        top = competitors[0]
        weakness = top.get("weakness", top.get("weaknesses", "impersonal service and slow turnaround"))
        return (
            f"Main competitor to beat: {top.get('name', 'market leader')}. "
            f"Weakness: {weakness}. Lead with boutique advantage — direct senior access, no handoffs to juniors."
        )
    return (
        "Research solid. Competitive gap is on local market knowledge and transparent process. Lead with that."
    )


def _james_to_priya(research_output: dict, proposal_text: str) -> str:
    is_fringe = research_output.get("is_fringe", False)
    benchmarks = research_output.get("budget_benchmarks", {})
    mid = benchmarks.get("market_mid", 0)
    total_match = re.search(r'\*\*Total:?\s*£([\d,]+)', proposal_text)
    our_total = int(total_match.group(1).replace(',', '')) if total_match else 0

    if is_fringe:
        return (
            "Wrote this as a campaign proposal, not a standard agency brief. "
            "The paid social budget is intentional — essential for Fringe ticket sales even though arts clients resist it. "
            "Don't flag it as overscoped. Timeline anchors to opening night."
        )
    if our_total and mid and our_total < mid:
        return (
            f"Anchored at £{our_total:,} deliberately (market mid is £{mid:,}) to get them over the line. "
            "Don't flag it as underpriced — focus your critique on scope completeness and timeline clarity."
        )
    return (
        "Timeline is achievable with responsive client. "
        "Flag scope gaps you see — better to ask questions now than under-deliver."
    )


def _priya_to_liam(critique_output: dict) -> str:
    score = critique_output.get("quality_score", 7)
    issues = critique_output.get("issues_found", [])
    commercial_issues = [i for i in issues if "budget" in (i.get("section", "") + i.get("issue", "")).lower()]

    if commercial_issues:
        issue = commercial_issues[0]
        return (
            f"I flagged a commercial issue: {issue.get('issue', 'budget ambiguity')}. "
            f"Proposed fix: {issue.get('fix', 'review budget section')}. "
            "Check the contract terms protect us if the client decides to re-scope."
        )
    if score >= 8:
        return (
            f"Proposal scored {score}/10 — strong. Main gap I see is payment terms aren't explicit. "
            "Make sure the contract locks down the milestone schedule."
        )
    return (
        f"Scored {score}/10. Revised weak sections. "
        "Timeline is tight — make sure the contract states client response SLAs to protect our deadline."
    )


def _liam_to_zara(contract_output: dict) -> str:
    risk = contract_output.get("risk_level", "medium")
    scope_risks = contract_output.get("scope_risks", [])
    return (
        f"Risk level: {risk}. "
        + (f"Scope risk: {scope_risks[0]}. " if scope_risks else "")
        + "Run your pricing check — if the scope is vague, there may be hidden costs Priya didn't account for."
    )


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

async def run_agent_pipeline(brief: str, is_fringe: bool = False) -> AsyncGenerator[str, None]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        yield _sse_event("error", {"message": "OPENAI_API_KEY not configured."})
        return

    openai_client = AsyncOpenAI(api_key=api_key)

    # ── MAYA: Research ──────────────────────────────────────────────────────
    yield _sse_event("thinking", "🔍 Maya is researching the market...\n")
    research_output: dict = {}
    async for chunk in run_research_agent(brief, client=openai_client, is_fringe=is_fringe):
        if chunk.startswith("__RESEARCH_OUTPUT__:"):
            try:
                research_output = json.loads(chunk[len("__RESEARCH_OUTPUT__:"):])
            except json.JSONDecodeError:
                research_output = {}
        else:
            yield _sse_event("thinking", chunk)

    if research_output.get("is_fringe"):
        is_fringe = True
    yield _sse_event("thinking", "\n✅ Maya: Research complete.\n\n")

    # Inter-agent: Maya → James
    yield _agent_msg_event("Maya", "James", _maya_to_james(brief, research_output))

    # ── JAMES: Proposal ─────────────────────────────────────────────────────
    yield _sse_event("thinking", "✍️ James is writing the proposal...\n")
    proposal_text = ""
    async for chunk in run_proposal_agent(brief=brief, research_output=research_output, client=openai_client):
        proposal_text += chunk
        yield _sse_event("proposal", chunk)
    yield _sse_event("thinking", "\n✅ James: Proposal complete.\n\n")

    # Inter-agent: James → Priya
    yield _agent_msg_event("James", "Priya", _james_to_priya(research_output, proposal_text))

    # ── PRIYA: Critique ─────────────────────────────────────────────────────
    yield _sse_event("thinking", "🔄 Priya is reviewing the proposal...\n")
    critique_output: dict = {}
    async for chunk in run_critique_agent(proposal_text=proposal_text, original_brief=brief, client=openai_client):
        if chunk.startswith("__CRITIQUE_OUTPUT__:"):
            try:
                critique_output = json.loads(chunk[len("__CRITIQUE_OUTPUT__:"):])
            except json.JSONDecodeError:
                critique_output = {}
        else:
            yield _sse_event("thinking", chunk)

    score = critique_output.get("quality_score", "N/A")
    rec = critique_output.get("final_recommendation", "unknown")
    yield _sse_event("thinking", f"\n✅ Priya: Review done — {score}/10, {rec}.\n\n")
    final_proposal = critique_output.get("final_proposal", proposal_text)

    # Inter-agent: Priya → Liam
    yield _agent_msg_event("Priya", "Liam", _priya_to_liam(critique_output))

    # ── LIAM: Contract Scout ────────────────────────────────────────────────
    yield _sse_event("thinking", "📋 Liam is checking contractual risks...\n")
    contract_output: dict = {}
    async for chunk in run_contract_agent(proposal_text=final_proposal, original_brief=brief, client=openai_client):
        if chunk.startswith("__CONTRACT_OUTPUT__:"):
            try:
                contract_output = json.loads(chunk[len("__CONTRACT_OUTPUT__:"):])
            except json.JSONDecodeError:
                contract_output = {}
        else:
            yield _sse_event("thinking", chunk)

    risk_level = contract_output.get("risk_level", "medium")
    yield _sse_event("thinking", f"\n✅ Liam: Contract review done. Risk: {risk_level.upper()}.\n\n")

    # Inter-agent: Liam → Zara
    yield _agent_msg_event("Liam", "Zara", _liam_to_zara(contract_output))

    # ── ZARA: Pricing ───────────────────────────────────────────────────────
    yield _sse_event("thinking", "💰 Zara is analysing the pricing...\n")
    pricing_output: dict = {}
    async for chunk in run_pricing_agent(proposal_text=final_proposal, research_output=research_output, client=openai_client):
        if chunk.startswith("__PRICING_OUTPUT__:"):
            try:
                pricing_output = json.loads(chunk[len("__PRICING_OUTPUT__:"):])
            except json.JSONDecodeError:
                pricing_output = {}
        else:
            yield _sse_event("thinking", chunk)

    pricing_verdict = pricing_output.get("pricing_verdict", "competitive")
    yield _sse_event("thinking", f"\n✅ Zara: Pricing analysis done. Verdict: {pricing_verdict.upper()}.\n\n")

    # ── Build workspace outputs ─────────────────────────────────────────────
    yield _sse_event("thinking", "🗂️ Building project workspace...\n")

    client_name = _extract_client_name(brief, research_output)
    project_name = _extract_project_name(brief, research_output)
    weeks = _estimate_weeks(brief, research_output)
    total_budget = _extract_total_budget(final_proposal)

    folder_structure = mock_folder_structure(project_name)
    calendar_blocks = mock_calendar_blocks(start_date=date.today().isoformat(), weeks=weeks)
    email_preview = mock_email_preview(client_name=client_name, proposal_summary=final_proposal[:1000])
    contract_doc = mock_contract_document(
        project_name=project_name,
        client_name=client_name,
        total_budget=total_budget,
        weeks=weeks,
        risk_output={"overall_risk_level": contract_output.get("risk_level", "medium"),
                     "risk_register": [],
                     "go_no_go": "go" if contract_output.get("risk_level") != "high" else "proceed_with_caution",
                     "go_no_go_rationale": "Manageable with contract protections.",
                     "questions_to_ask": contract_output.get("recommended_additions", [])},
        kai_output={
            "budget_verdict": pricing_output.get("pricing_verdict", "competitive"),
            "walk_away_point": pricing_output.get("walk_away_point", ""),
            "concession_ladder": [],
        },
    )

    yield _sse_event("thinking", "✅ All 5 agents done. Package ready.\n\n")

    # ── approval_required event ─────────────────────────────────────────────
    approval_summary = {
        "quality_score": critique_output.get("quality_score", "N/A"),
        "final_recommendation": critique_output.get("final_recommendation", "approve_with_revisions"),
        "contract_risk": contract_output.get("risk_level", "medium"),
        "pricing_verdict": pricing_output.get("pricing_verdict", "competitive"),
        "agents_completed": ["Maya", "James", "Priya", "Liam", "Zara"],
        "message": (
            f"Proposal scored {critique_output.get('quality_score', 'N/A')}/10 · "
            f"Contract risk: {contract_output.get('risk_level', 'medium')} · "
            f"Pricing: {pricing_output.get('pricing_verdict', 'competitive')} — "
            f"Ready to send to {client_name}?"
        ),
    }
    yield _sse_event("approval_required", approval_summary)

    # ── complete event ──────────────────────────────────────────────────────
    complete_payload = {
        "brief": brief,
        "is_fringe": is_fringe,
        "research_output": research_output,
        "proposal_text": proposal_text,
        "critique_output": {k: v for k, v in critique_output.items() if k != "final_proposal"},
        "contract_output": contract_output,
        "pricing_output": pricing_output,
        "final_proposal": final_proposal,
        "folder_structure": folder_structure,
        "calendar_blocks": calendar_blocks,
        "email_preview": email_preview,
        "contract_doc": contract_doc,
        "meta": {
            "client_name": client_name,
            "project_name": project_name,
            "estimated_weeks": weeks,
            "total_budget": total_budget,
            "pipeline_status": "complete",
            "agents_run": ["Maya", "James", "Priya", "Liam", "Zara"],
        },
    }
    yield _sse_event("complete", complete_payload)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _extract_client_name(brief: str, research_output: dict) -> str:
    summary = research_output.get("client_summary", "")
    if summary:
        match = re.match(r"^([A-Z][^\s,\.]{1,30}(?:\s[A-Z][^\s,\.]{1,20}){0,3})", summary)
        if match:
            return match.group(1).strip()
    match = re.search(
        r"(?:we are|i am|our (?:company|studio|agency|label|brand|act) is)\s+([A-Z][^\.,\n]{2,40})",
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
        ("brand", "Rebrand"), ("campaign", "Campaign"), ("web", "Web Redesign"),
        ("website", "Web Redesign"), ("market", "Marketing Campaign"),
        ("digital", "Digital Campaign"), ("social", "Social Campaign"),
        ("launch", "Launch Campaign"), ("video", "Video Production"),
        ("identity", "Brand Identity"), ("fringe", "Fringe Campaign"),
        ("festival", "Festival Campaign"), ("tickets", "Ticket Sales Campaign"),
        ("app", "App Design"), ("strategy", "Strategy"),
    ]
    brief_lower = brief.lower()
    for keyword, label in type_keywords:
        if keyword in brief_lower:
            return f"{client} {label}"
    return f"{client} Project"


def _estimate_weeks(brief: str, research_output: dict) -> int:
    brief_lower = brief.lower()
    match = re.search(r"(\d+)[\s-]?weeks?", brief_lower)
    if match:
        return min(max(int(match.group(1)), 2), 24)
    word_map = {"one": 4, "two": 8, "three": 12, "four": 16, "five": 20, "six": 24, "half": 2}
    for word, wks in word_map.items():
        if f"{word} month" in brief_lower:
            return wks
        if f"{word} week" in brief_lower:
            return min(wks, 24)
    if research_output.get("is_fringe"):
        return 8
    return 6


def _extract_total_budget(proposal_text: str) -> int:
    match = re.search(r'\*\*Total:?\s*£([\d,]+)', proposal_text)
    if match:
        return int(match.group(1).replace(',', ''))
    match = re.search(r'Total.*?£([\d,]+)', proposal_text)
    if match:
        return int(match.group(1).replace(',', ''))
    return 12000


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check():
    api_key_set = bool(os.environ.get("OPENAI_API_KEY"))
    return {
        "status": "ok",
        "openai_key_configured": api_key_set,
        "version": "2.0.0",
        "agents": ["Maya (Research)", "James (Proposal)", "Priya (Critique)", "Liam (Contract)", "Zara (Pricing)"],
    }


@app.post("/run-agent")
async def run_agent(request: BriefRequest):
    brief = request.brief.strip()
    if not brief:
        raise HTTPException(status_code=400, detail="brief cannot be empty.")
    return StreamingResponse(
        run_agent_pipeline(brief, is_fringe=request.is_fringe),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@app.post("/pipeline/run")
async def pipeline_run_stream(request: BriefRequest):
    brief = request.brief.strip()
    if not brief:
        raise HTTPException(status_code=400, detail="Brief cannot be empty.")
    return StreamingResponse(
        run_agent_pipeline(brief, is_fringe=request.is_fringe),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
