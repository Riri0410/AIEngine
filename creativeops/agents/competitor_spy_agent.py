"""
Competitor Spy Agent — Alex Kim, Competitive Intelligence
Agent 4: Deep-dives on named competitors and generates positioning strategy.

Knows EXACTLY which agencies are competing for this client and how to beat each one.
"""

import json
import os
from typing import AsyncGenerator

from openai import AsyncOpenAI

from tools.web_search import WEB_SEARCH_TOOL_SCHEMA, handle_tool_call

ALEX_SYSTEM_PROMPT = """You are Alex Kim, Competitive Intelligence Analyst at CreativeOps Studio.
You are sharp, strategic, and slightly obsessive about knowing what competitors are up to.

ALWAYS prefix every line with "[Alex]".

You research the SPECIFIC competitors in the client's city and produce a tactical playbook for James to use:
- What is each competitor's biggest weakness we can exploit?
- What would they pitch for this brief? (so we can differentiate)
- What's our single strongest "killer line" against each one?

You have web_search. Use it to find competitor data for the client's location.

After searching, output 2-3 "[Alex]" lines summarising what you found, then output ONLY valid JSON:
{
  "top_competitors": [
    {
      "name": "Agency Name",
      "likely_pitch": "What they'd probably say in their proposal",
      "weakness": "Their specific weakness we can exploit",
      "killer_line": "The one thing we say if the client is considering them",
      "avg_project_value": "£X–£Y"
    }
  ],
  "our_positioning": "One sentence: how we position CreativeOps against this field",
  "differentiator_stack": ["Point 1 that none of them can match", "Point 2", "Point 3"],
  "red_flags": ["Any competitor we should be worried about and why"],
  "agent_confidence": 88
}"""


async def run_competitor_spy_agent(
    brief: str,
    research_output: dict,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    yield "[Alex] Running competitive intelligence sweep. Let's see who else is pitching for this.\n"

    is_fringe = research_output.get("is_fringe", False)
    existing_competitors = research_output.get("competitors", [])

    # Determine city from brief
    city = "Edinburgh"
    brief_lower = brief.lower()
    if "glasgow" in brief_lower:
        city = "Glasgow"
    elif "dundee" in brief_lower:
        city = "Dundee"

    yield f"[Alex] Client appears to be in {city}. Mapping the competitive landscape now.\n"

    user_message = f"""Brief:
{brief[:600]}

Existing competitor data from Maya's research:
{json.dumps(existing_competitors, indent=2)}

City: {city}
Fringe/Arts: {is_fringe}

Search for competitor agencies in {city} and produce a tactical competitive playbook.
{"Focus on agencies that pitch to arts/events clients." if is_fringe else ""}

Write [Alex] commentary (2-3 lines) then output the JSON:"""

    messages = [
        {"role": "system", "content": ALEX_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # One targeted search
    search_topic = "competitor_analysis_edinburgh_agencies" if city == "Edinburgh" else "competitor_analysis_glasgow_agencies"
    yield f"[Alex] 🔍 Pulling {city} agency data...\n"
    search_result = handle_tool_call("web_search", json.dumps({
        "query": f"top creative agencies {city} 2024 competitors",
        "topic": search_topic,
    }))
    messages.append({
        "role": "user",
        "content": f"Search results: {search_result}\n\nNow produce your competitive intelligence JSON:"
    })

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
        max_tokens=1200,
    )

    raw = response.choices[0].message.content or ""

    chunk_size = 10
    for i in range(0, len(raw), chunk_size):
        yield raw[i: i + chunk_size]

    alex_data = _parse_alex_output(raw)
    top = alex_data.get("top_competitors", [])
    yield f"\n[Alex] ✅ Intel complete. {len(top)} competitors mapped. Our positioning is set.\n"
    yield f"\n__ALEX_OUTPUT__:{json.dumps(alex_data)}"


def _parse_alex_output(raw: str) -> dict:
    text = raw.strip()
    json_start = text.find('{')
    if json_start >= 0:
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
            "top_competitors": [],
            "our_positioning": "Boutique Scottish agency with senior-led delivery and transparent pricing.",
            "differentiator_stack": [
                "Direct access to Creative Director on every project",
                "Transparent day rates, no hidden fees",
                "Deep Scottish market knowledge"
            ],
            "red_flags": [],
            "agent_confidence": 55,
        }
