"""
Research Agent — Agent 1 of the CreativeOps pipeline.
Enhanced with agent voice narration and Fringe/SME mode awareness.
"""

import json
import os
from typing import AsyncGenerator

from openai import AsyncOpenAI

from tools.web_search import WEB_SEARCH_TOOL_SCHEMA, handle_tool_call
from mock_data.past_clients import get_relevant_clients, format_client_context

ResearchOutput = dict

RESEARCH_SYSTEM_PROMPT = """You are Maya, a senior research analyst at CreativeOps Studio in Edinburgh.
You're sharp, direct, and obsessed with Scottish market nuance. You know which agencies are threats,
which sectors are growing, and exactly what budgets look like on the ground.

As you research, narrate your thinking out loud — what you're finding, why it matters,
what surprises you, what it means for the proposal. Be specific and human.

You have access to a web_search tool. Call it at least 3 times to gather:
1. Industry/market overview for the client's sector
2. Competitor landscape (Edinburgh or Glasgow agencies)
3. Budget benchmarks for this project type

After searching, return ONLY valid JSON (no markdown fences):
{
  "client_summary": "2-3 sentence overview of the client, their sector, and what they need",
  "industry_context": "Key market facts relevant to this brief",
  "competitors": [
    {"name": "Agency Name", "strengths": "...", "avg_project_value": "£X-£Y", "why_client_might_consider": "..."}
  ],
  "market_insights": "Key insights that should shape our proposal",
  "budget_benchmarks": {
    "market_low": 0,
    "market_mid": 0,
    "market_high": 0,
    "recommended_budget": 0,
    "notes": "Rationale"
  },
  "strategic_recommendations": ["rec 1", "rec 2", "rec 3"],
  "risk_flags": ["risk 1", "risk 2"],
  "confidence_score": 85,
  "relevant_past_clients_recalled": ["Past Client A"],
  "is_arts_client": false,
  "is_fringe_act": false
}"""

FRINGE_RESEARCH_SYSTEM_PROMPT = """You are Maya, senior research analyst at CreativeOps Studio.
You specialise in Edinburgh Fringe acts and Scottish arts marketing. You know Pleasance, Gilded
Balloon, Assembly, Underbelly inside out. You know what sells shows and what doesn't.

Narrate your thinking as you research — what the act needs, who their audience is,
what the Fringe marketing landscape looks like, realistic ticket targets.

Call web_search at least 3 times, then return ONLY valid JSON (no markdown fences):
{
  "client_summary": "Overview of the act and their Fringe ambitions",
  "industry_context": "Fringe marketing landscape, audience behaviours, press dynamics",
  "competitors": [
    {"name": "Similar Act Type", "strengths": "What makes them sell out", "avg_project_value": "£X-£Y", "why_client_might_consider": "..."}
  ],
  "market_insights": "What actually sells Fringe shows in 2025",
  "budget_benchmarks": {
    "market_low": 0,
    "market_mid": 0,
    "market_high": 0,
    "recommended_budget": 0,
    "notes": "Fringe-specific rationale"
  },
  "strategic_recommendations": ["rec 1", "rec 2", "rec 3"],
  "risk_flags": ["risk 1", "risk 2"],
  "confidence_score": 85,
  "relevant_past_clients_recalled": ["Past Client A"],
  "is_arts_client": true,
  "is_fringe_act": true
}"""


def _detect_fringe(brief: str) -> bool:
    fringe_keywords = [
        "fringe", "pleasance", "gilded balloon", "assembly rooms", "underbelly",
        "spoken word", "comedy act", "theatre act", "show at", "performing at",
        "edinburgh show", "august festival", "sell tickets", "sell out"
    ]
    brief_lower = brief.lower()
    return any(kw in brief_lower for kw in fringe_keywords)


async def run_research_agent(
    brief: str,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    is_fringe = _detect_fringe(brief)
    system_prompt = FRINGE_RESEARCH_SYSTEM_PROMPT if is_fringe else RESEARCH_SYSTEM_PROMPT

    relevant_clients = get_relevant_clients(brief)
    past_context = format_client_context(relevant_clients)

    # Agent voice — narrate what we're starting
    if is_fringe:
        yield "\n💭 [Maya] This is a Fringe act. Different playbook entirely — press previews, flyering strategy, social proof from reviewers. Let me pull the Fringe-specific data...\n"
    else:
        yield "\n💭 [Maya] Right, let me figure out who this client is up against and what a realistic budget looks like for the Scottish market...\n"

    user_message = f"""New client brief:

---
{brief}
---

{past_context}

Research this thoroughly using web_search, narrate your key findings as you go, then return your structured JSON report."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    tool_call_rounds = 0
    MAX_TOOL_ROUNDS = 6

    while tool_call_rounds < MAX_TOOL_ROUNDS:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=[WEB_SEARCH_TOOL_SCHEMA],
            tool_choice="auto",
            temperature=0.3,
        )

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls":
            tool_calls = choice.message.tool_calls
            messages.append(choice.message)

            for tc in tool_calls:
                tool_args = tc.function.arguments
                query = json.loads(tool_args).get('query', '')

                # Agent voice on each search
                yield f"\n🔎 [Maya] Searching: {query}...\n"

                result_str = handle_tool_call(tc.function.name, tool_args)
                result_data = json.loads(result_str)

                # Narrate what was found
                if result_data.get("status") == "success":
                    summary = result_data.get("result", {}).get("summary", "")
                    if summary:
                        # Pull first interesting sentence as a voice line
                        first_sentence = summary.split(".")[0] + "."
                        yield f"💭 [Maya] Got it — {first_sentence}\n"

                # Narrate past client memory recall if present
                if past_context and tool_call_rounds == 0 and "client" in query.lower():
                     yield f"💭 [Maya] Checking our past files... Ah, I remember {relevant_clients[0]['name']} — similar budget, we can use those learnings.\n"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

            tool_call_rounds += 1
            continue

        if choice.finish_reason in ("stop", "length"):
            final_content = choice.message.content or ""

            # Stream the thinking/narration parts (non-JSON lines)
            lines = final_content.split("\n")
            json_start = -1
            for i, line in enumerate(lines):
                if line.strip().startswith("{"):
                    json_start = i
                    break

            if json_start > 0:
                narration = "\n".join(lines[:json_start])
                for line in narration.split("\n"):
                    if line.strip():
                        yield f"💭 [Maya] {line.strip()}\n"

            # Added as requested for "wow" factor
            yield f"💭 [Maya] Passing a note to James: Watch out, their budget is often below market — position carefully.\n"

            yield f"\n✅ [Maya] Research complete. Handing findings to the proposal team.\n\n"

            research_data = _parse_research_output(final_content)
            research_data["is_fringe_act"] = is_fringe
            research_data["is_arts_client"] = is_fringe

            yield f"\n__RESEARCH_OUTPUT__:{json.dumps(research_data)}"
            return

        yield f"\n[Research agent stopped: {choice.finish_reason}]\n"
        return

    yield "\n[Research agent hit tool call limit — returning partial data]\n"


def _parse_research_output(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = inner.strip()

    # Try to find JSON block if mixed with narration
    import re
    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        text = json_match.group(0)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "client_summary": "Research completed.",
            "industry_context": raw[:500],
            "competitors": [],
            "market_insights": "",
            "budget_benchmarks": {
                "market_low": 0, "market_mid": 0,
                "market_high": 0, "recommended_budget": 0,
                "notes": "Could not parse structured benchmarks.",
            },
            "strategic_recommendations": [],
            "risk_flags": [],
            "confidence_score": 50,
            "relevant_past_clients_recalled": [],
            "is_fringe_act": False,
            "is_arts_client": False,
            "_raw": raw,
        }