"""
Pricing Strategist Agent — Zara Okonkwo
Cross-checks budget against Scottish market benchmarks.
Flags underpricing and finds upsell opportunities.
Emits 💭 [Zara] voice lines and returns __PRICING_OUTPUT__: JSON.
"""

import json
import os
import re
from typing import AsyncGenerator

from openai import AsyncOpenAI

ZARA_SYSTEM_PROMPT = """You are Zara Okonkwo, Pricing Strategist at CreativeOps Studio.
You protect the agency's margins and make sure we never leave money on the table.

ALWAYS prefix every line with "[Zara]".

Cross-check the proposal's budget against Scottish market benchmarks and find:
1. Is our total price under/at/above market rate?
2. Are there deliverables we're providing for free that should be charged?
3. What upsell opportunities exist — what would the client naturally want to add next?
4. What's the negotiation strategy if they push back on price?

Write 3-4 "[Zara]" lines with your assessment, then output ONLY valid JSON (no markdown fences):
{
  "pricing_verdict": "underpriced|competitive|premium",
  "market_position_percentile": 65,
  "budget_health": {
    "our_total": 14500,
    "market_low": 8000,
    "market_mid": 18000,
    "market_high": 35000,
    "variance_from_mid": "-19%"
  },
  "underpriced_items": [
    {"item": "Photography direction", "our_charge": 0, "market_rate": "£600–£900", "note": "Included but not itemised"}
  ],
  "upsell_opportunities": [
    {"service": "Monthly social media retainer", "value": "£1,500–£2,500/month", "timing": "Propose at delivery meeting"},
    {"service": "SEO audit and strategy", "value": "£1,200", "timing": "Mention in proposal next steps"}
  ],
  "negotiation_note": "If they push back: offer to remove photography, saving £750, keeping core deliverables intact.",
  "walk_away_point": "£11,500 — below this margin is less than 18%",
  "agent_confidence": 91
}"""


async def run_pricing_agent(
    proposal_text: str,
    research_output: dict,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    yield "[Zara] Running pricing analysis. Let me see if we're leaving money on the table.\n"

    benchmarks = research_output.get("budget_benchmarks", {})
    stated_budget = research_output.get("stated_budget", 0)

    total_match = re.search(r'\*\*Total:?\s*£([\d,]+)', proposal_text)
    our_total = int(total_match.group(1).replace(',', '')) if total_match else 0

    mid = benchmarks.get("market_mid") or benchmarks.get("recommended_budget", 0)
    if our_total and mid:
        pct = int((our_total / mid) * 100)
        if pct < 80:
            yield f"[Zara] We're pricing at {pct}% of market mid. That's underpriced. I'll flag what we should be charging for separately.\n"
        elif pct > 110:
            yield f"[Zara] We're at {pct}% of market mid — premium. Every line item needs to be justifiable.\n"
        else:
            yield f"[Zara] Pricing looks competitive at {pct}% of market mid. Upsell opportunities are the focus here.\n"

    user_message = f"""Analyse the pricing in this proposal.

## Market Benchmarks
{json.dumps(benchmarks, indent=2)}
Stated client budget: £{stated_budget:,}

## Proposal (budget section focus)
{proposal_text[-2500:]}

Write 3-4 [Zara] commentary lines, then output the JSON pricing analysis:"""

    messages = [
        {"role": "system", "content": ZARA_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
        max_tokens=1000,
    )

    raw = response.choices[0].message.content or ""

    chunk_size = 10
    for i in range(0, len(raw), chunk_size):
        yield raw[i: i + chunk_size]

    pricing_data = _parse_output(raw)
    verdict = pricing_data.get("pricing_verdict", "competitive")
    yield f"\n[Zara] ✅ Pricing analysis done. Verdict: {verdict.upper()}.\n"
    yield f"\n__PRICING_OUTPUT__:{json.dumps(pricing_data)}"


def _parse_output(raw: str) -> dict:
    text = raw.strip()
    json_start = text.find('{')
    if json_start >= 0:
        try:
            return json.loads(text[json_start:])
        except json.JSONDecodeError:
            pass
    return {
        "pricing_verdict": "competitive",
        "market_position_percentile": 60,
        "budget_health": {},
        "underpriced_items": [],
        "upsell_opportunities": [
            {"service": "Monthly retainer", "value": "£1,500–£2,500/month", "timing": "Propose at delivery meeting"},
        ],
        "negotiation_note": "If they push back, offer to remove one deliverable phase and re-scope.",
        "walk_away_point": "20% below proposed total",
        "agent_confidence": 60,
    }
