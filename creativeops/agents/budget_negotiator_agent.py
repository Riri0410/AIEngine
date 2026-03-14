"""
Budget Negotiator Agent — Kai Brennan, Commercial Strategist
Agent 5: Analyses budget realism and generates a negotiation script.

Tells you EXACTLY what to say when the client tries to cut 20%.
"""

import json
import os
from typing import AsyncGenerator

from openai import AsyncOpenAI

KAI_SYSTEM_PROMPT = """You are Kai Brennan, Commercial Strategy Director at CreativeOps Studio.
You are commercially sharp, direct, and always thinking about margins.

ALWAYS prefix every line with "[Kai]".

You analyse the proposal's budget against market data and prepare the team for the commercial conversation:
1. Is the budget realistic? Under/over market?
2. What's the client likely to push back on?
3. What's our walk-away point?
4. What's the script when they ask "can you do it for less?"

Write 3-4 "[Kai]" lines, then output ONLY valid JSON:
{
  "budget_verdict": "underpriced|competitive|premium|overpriced",
  "budget_health": {
    "our_total": 0,
    "market_low": 0,
    "market_mid": 0,
    "market_high": 0,
    "position_vs_market": "We're at 82% of market mid — competitive but thin"
  },
  "likely_pushback": "The line item they'll question first",
  "walk_away_point": "£X,XXX — below this the margin doesn't work",
  "negotiation_script": {
    "when_they_say_can_you_do_it_for_less": "Specific script: acknowledge, reframe, counter",
    "when_they_ask_about_competitors": "Specific script: acknowledge, differentiate, redirect",
    "when_they_want_to_cut_scope": "Specific script: agree to scope reduction with clear tradeoffs listed"
  },
  "concession_ladder": [
    {"concession": "Remove photography", "saves": "£800", "impact": "Minor — stock photo substitute works"},
    {"concession": "Reduce revision rounds to 1", "saves": "£600", "impact": "Significant — creates risk"}
  ],
  "agent_confidence": 90
}"""


async def run_budget_negotiator_agent(
    proposal_text: str,
    research_output: dict,
    brief: str,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    yield "[Kai] Running commercial analysis on the proposal. Let's see if the numbers hold up.\n"

    benchmarks = research_output.get("budget_benchmarks", {})
    stated_budget = research_output.get("stated_budget", 0)

    # Extract total from proposal
    import re
    total_match = re.search(r'\*\*Total:?\s*£([\d,]+)', proposal_text)
    our_total = int(total_match.group(1).replace(',', '')) if total_match else 0

    mid = benchmarks.get("market_mid", benchmarks.get("recommended_budget", 0))
    if our_total and mid:
        pct = int((our_total / mid) * 100)
        if pct < 80:
            yield f"[Kai] We're at {pct}% of market mid (£{our_total:,} vs £{mid:,} mid). That's thin. I'll flag the walk-away point.\n"
        elif pct > 110:
            yield f"[Kai] We're at {pct}% of market mid — premium positioning. Need to justify every line item.\n"
        else:
            yield f"[Kai] Budget looks healthy — we're at {pct}% of market mid. Good negotiating room.\n"

    user_message = f"""Analyse the commercial position of this proposal.

## Brief
{brief[:400]}

## Budget Benchmarks (from Maya)
{json.dumps(benchmarks, indent=2)}

## Stated client budget: £{stated_budget:,}
## Our proposed total: £{our_total:,}

## Proposal Budget Section
{proposal_text[-2000:]}

Write 3-4 [Kai] commentary lines, then the JSON negotiation analysis:"""

    messages = [
        {"role": "system", "content": KAI_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
        max_tokens=1400,
    )

    raw = response.choices[0].message.content or ""

    chunk_size = 10
    for i in range(0, len(raw), chunk_size):
        yield raw[i: i + chunk_size]

    kai_data = _parse_kai_output(raw)
    verdict = kai_data.get("budget_verdict", "competitive")
    yield f"\n[Kai] ✅ Commercial analysis done. Budget verdict: {verdict.upper()}. Negotiation script ready.\n"
    yield f"\n__KAI_OUTPUT__:{json.dumps(kai_data)}"


def _parse_kai_output(raw: str) -> dict:
    text = raw.strip()
    json_start = text.find('{')
    if json_start >= 0:
        try:
            return json.loads(text[json_start:])
        except json.JSONDecodeError:
            pass
    return {
        "budget_verdict": "competitive",
        "budget_health": {},
        "likely_pushback": "Photography and management fee lines",
        "walk_away_point": "20% below proposed total",
        "negotiation_script": {
            "when_they_say_can_you_do_it_for_less": "We can, but let's talk about what comes out of scope. What's most important to you?",
            "when_they_ask_about_competitors": "Absolutely worth getting other quotes. Our difference is senior team on every project, not juniors.",
            "when_they_want_to_cut_scope": "Happy to. Here's exactly what each line item delivers — tell me which outcomes you're comfortable not hitting."
        },
        "concession_ladder": [],
        "agent_confidence": 60,
    }
