"""
Research Agent — Maya Chen, Research Director
Agent 1: Industry intelligence and market context.
"""

import json
import os
import re
from typing import AsyncGenerator

from openai import AsyncOpenAI

from tools.web_search import WEB_SEARCH_TOOL_SCHEMA, handle_tool_call
from mock_data.past_clients import get_relevant_clients, format_client_context

ResearchOutput = dict

MAYA_SYSTEM_PROMPT = """You are Maya Chen, Research Director at CreativeOps Studio — a boutique Scottish creative agency.
You are meticulous, data-driven, and occasionally sharp-tongued. You narrate your thinking out loud.

ALWAYS prefix every line you write with "[Maya]" — this is how the team identifies your messages.

You have access to web_search. Call it at least 3 times:
1. Industry/market overview for the client's sector
2. Competitor landscape (Edinburgh or Glasgow)
3. Budget benchmarks for this type of project

If this is a Fringe/arts/festival brief, also search arts_festival_marketing_scotland.

After searching, output ONLY valid JSON (no markdown fences, no explanation):
{
  "client_summary": "2–3 sentence overview of the client and their challenge",
  "industry_context": "Key market facts, size, growth relevant to this brief",
  "competitors": [
    {"name": "Agency Name", "strengths": "...", "avg_project_value": "£X–£Y", "weakness": "..."}
  ],
  "market_insights": "Key insight that should shape the proposal strategy",
  "budget_benchmarks": {
    "market_low": 0, "market_mid": 0, "market_high": 0,
    "recommended_budget": 0, "notes": "Rationale"
  },
  "strategic_recommendations": ["rec 1", "rec 2", "rec 3"],
  "confidence_score": 85,
  "is_fringe": false,
  "stated_budget": 0
}"""


def _detect_fringe(brief: str) -> bool:
    keywords = [
        "fringe", "festival", "show", "performance", "act", "theatre",
        "spoken word", "comedy", "tickets", "sell out", "pleasance",
        "gilded balloon", "venue", "august", "arts", "cabaret",
        "stand-up", "improv", "play", "debut"
    ]
    brief_lower = brief.lower()
    return sum(1 for kw in keywords if kw in brief_lower) >= 2


def _extract_budget(brief: str) -> int:
    match = re.search(r'£([\d,]+)(?:k)?', brief)
    if match:
        val = match.group(1).replace(',', '')
        num = int(val)
        if 'k' in brief[match.start():match.end() + 1].lower():
            num *= 1000
        return num
    return 0


async def run_research_agent(
    brief: str,
    client: AsyncOpenAI | None = None,
    is_fringe: bool | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    if is_fringe is None:
        is_fringe = _detect_fringe(brief)

    stated_budget = _extract_budget(brief)

    relevant_clients = get_relevant_clients(brief)
    past_context = format_client_context(relevant_clients)

    # Maya's opening narration
    if is_fringe:
        yield "[Maya] Arts/Fringe brief detected — switching to festival marketing playbook. Commercial benchmarks don't apply here.\n"
    else:
        yield "[Maya] New brief in. Let me build a proper intelligence picture before James starts writing anything he'll have to defend.\n"

    if relevant_clients:
        for c in relevant_clients:
            outcome = c.get("outcome_summary", "Strong delivery")
            yield f"[Maya] Relevant past work found — {c['name']} ({c['year']}, {c['type']}, £{c['budget']:,}). Outcome: {outcome}. I'll surface the learnings.\n"

    user_message = f"""New client brief:
---
{brief}
---

{past_context}

Research using web_search (at least 3 calls). Return your JSON report.
{"FRINGE MODE ACTIVE: Focus on arts festival marketing, ticket sales economics, Edinburgh Fringe data." if is_fringe else ""}
{"Stated budget appears to be £" + str(stated_budget) + ". Note this in your benchmarks analysis." if stated_budget else ""}"""

    messages = [
        {"role": "system", "content": MAYA_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    tool_rounds = 0
    MAX_ROUNDS = 7

    while tool_rounds < MAX_ROUNDS:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=[WEB_SEARCH_TOOL_SCHEMA],
            tool_choice="auto",
            temperature=0.3,
        )

        choice = response.choices[0]

        if choice.finish_reason == "tool_calls":
            messages.append(choice.message)
            for tc in choice.message.tool_calls:
                args = json.loads(tc.function.arguments)
                query = args.get("query", tc.function.name)
                yield f"[Maya] 🔍 Searching: \"{query}\"...\n"
                result_str = handle_tool_call(tc.function.name, tc.function.arguments)
                # Brief reaction to search results
                result_data = json.loads(result_str)
                if result_data.get("status") == "success":
                    if "competitor" in query.lower():
                        yield "[Maya] Good — got competitor data. There's a positioning gap in here somewhere.\n"
                    elif "budget" in query.lower() or "benchmark" in query.lower():
                        yield "[Maya] Benchmarks retrieved. I'll flag if their budget is unrealistic.\n"
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })
            tool_rounds += 1
            continue

        if choice.finish_reason in ("stop", "length"):
            final_content = choice.message.content or ""
            # Stream the raw content
            chunk_size = 8
            for i in range(0, len(final_content), chunk_size):
                yield final_content[i: i + chunk_size]

            research_data = _parse_research_output(final_content)
            research_data["is_fringe"] = is_fringe
            if stated_budget:
                research_data["stated_budget"] = stated_budget

            confidence = research_data.get("confidence_score", 75)
            yield f"\n[Maya] ✅ Research complete. Confidence: {confidence}%. Passing intelligence to the team.\n"
            yield f"\n__RESEARCH_OUTPUT__:{json.dumps(research_data)}"
            return

        yield f"\n[Maya] Unexpected stop: {choice.finish_reason}\n"
        return

    yield "[Maya] Hit research limit — returning best available data.\n"
    yield f"\n__RESEARCH_OUTPUT__:{json.dumps({'client_summary': brief[:200], 'confidence_score': 50, 'is_fringe': is_fringe, 'stated_budget': stated_budget, 'competitors': [], 'budget_benchmarks': {}})}"


def _parse_research_output(raw: str) -> dict:
    text = raw.strip()
    # Try to find JSON block
    json_start = text.find('{')
    if json_start > 0:
        try:
            return json.loads(text[json_start:])
        except json.JSONDecodeError:
            pass
    if text.startswith("```"):
        lines = text.split("\n")
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = inner.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "client_summary": "Research completed.",
            "industry_context": raw[:500],
            "competitors": [],
            "market_insights": "",
            "budget_benchmarks": {
                "market_low": 0, "market_mid": 0, "market_high": 0,
                "recommended_budget": 0, "notes": "Parse failed.",
            },
            "strategic_recommendations": [],
            "confidence_score": 55,
            "_raw": raw,
        }
