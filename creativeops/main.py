"""
CreativeOps AI — Cloudflare Workers Python Backend
Autonomous brief-to-proposal agent pipeline for creative agencies.

Endpoints:
  POST /run-agent             — SSE stream, typed events {type, content}
  POST /pipeline/run          — SSE stream of the full agent pipeline
  GET  /health                — Health check

Entry point: on_fetch(request, env) — Cloudflare Workers Python handler.
For local development, use main.py.bak (FastAPI version) instead.
"""

import json
import os
import sys
import re
import asyncio
from datetime import date
from typing import AsyncGenerator

sys.path.append(os.path.dirname(__file__))

from js import Response, Headers, TransformStream, TextEncoder
from openai import AsyncOpenAI

from agents.research_agent import run_research_agent
from agents.proposal_agent import run_proposal_agent
from agents.critique_agent import run_critique_agent
from tools.mock_outputs import mock_folder_structure, mock_calendar_blocks, mock_email_preview


# ---------------------------------------------------------------------------
# CORS helpers
# ---------------------------------------------------------------------------

_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def _make_headers(extra: dict = None) -> object:
    merged = {**_CORS_HEADERS, **(extra or {})}
    return Headers.new(list(merged.items()))


def _json_response(data, status: int = 200) -> object:
    return Response.new(
        json.dumps(data, ensure_ascii=False),
        status=status,
        headers=_make_headers({"Content-Type": "application/json"}),
    )


def _error_response(message: str, status: int = 400) -> object:
    return _json_response({"error": message}, status=status)


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse(data: str) -> str:
    lines = data.split("\n")
    formatted = "\n".join(f"data: {line}" for line in lines)
    return formatted + "\n\n"


def _sse_event(type_: str, content) -> str:
    event = {"type": type_, "content": content}
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# Agent pipeline orchestrators
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
    async for chunk in run_proposal_agent(
        brief=brief,
        research_output=research_output,
        client=openai_client,
    ):
        proposal_text += chunk
        yield _sse(f"✍️ PROPOSAL: {chunk}")

    yield _sse("\n✍️ PROPOSAL: ✅ Proposal draft complete.\n\n")
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
    async for chunk in run_proposal_agent(
        brief=brief,
        research_output=research_output,
        client=openai_client,
    ):
        proposal_text += chunk
        yield _sse_event("proposal", chunk)

    yield _sse_event("thinking", "\n✅ Proposal draft complete.\n\n")
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
# Metadata helpers
# ---------------------------------------------------------------------------

def _extract_client_name(brief: str, research_output: dict) -> str:
    summary = research_output.get("client_summary", "")
    if summary:
        match = re.match(r"^([A-Z][^\s,\.]{1,30}(?:\s[A-Z][^\s,\.]{1,20}){0,3})", summary)
        if match:
            return match.group(1).strip()

    match = re.search(
        r"(?:we are|i am|our (?:company|studio|agency|label|brand) is)\s+([A-Z][^\.,\n]{2,40})",
        brief,
        re.IGNORECASE,
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
        ("digital", "Digital Campaign"), ("social", "Social Media Campaign"),
        ("launch", "Launch Campaign"), ("video", "Video Production"),
        ("identity", "Brand Identity"), ("app", "App Design"),
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
# SSE streaming response via TransformStream
# ---------------------------------------------------------------------------

async def _sse_response(generator) -> object:
    transform = TransformStream.new()
    writer = transform.writable.getWriter()
    encoder = TextEncoder.new()

    async def _write():
        try:
            async for chunk in generator:
                await writer.write(encoder.encode(chunk))
        finally:
            await writer.close()

    asyncio.ensure_future(_write())

    headers = _make_headers({
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })
    return Response.new(transform.readable, status=200, headers=headers)


# ---------------------------------------------------------------------------
# Cloudflare Workers entry point
# ---------------------------------------------------------------------------

async def on_fetch(request, env):
    # Inject secrets from CF bindings into environment
    if hasattr(env, "OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = str(env.OPENAI_API_KEY)

    method = str(request.method)

    # Parse path from URL
    url = str(request.url)
    try:
        path = "/" + "/".join(url.split("://", 1)[1].split("/")[1:])
        path = path.split("?")[0].rstrip("/") or "/"
    except Exception:
        path = "/"

    # CORS preflight
    if method == "OPTIONS":
        return Response.new("", status=204, headers=_make_headers())

    # Health check
    if method == "GET" and path == "/health":
        return _json_response({
            "status": "ok",
            "openai_key_configured": bool(os.environ.get("OPENAI_API_KEY")),
            "version": "1.0.0",
        })

    # SSE endpoints
    if method == "POST" and path in ("/run-agent", "/pipeline/run"):
        try:
            body_text = await request.text()
            body_data = json.loads(body_text)
            brief = body_data.get("brief", "").strip()
        except Exception:
            return _error_response("Invalid JSON body")

        if not brief:
            return _error_response("brief cannot be empty")

        if path == "/run-agent":
            return await _sse_response(run_agent_pipeline(brief))
        else:
            return await _sse_response(run_full_pipeline(brief))

    return _error_response("Not found", status=404)
