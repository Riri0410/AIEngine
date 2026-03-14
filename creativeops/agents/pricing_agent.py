"""
Pricing Agent — Agent 5 of the CreativeOps pipeline.
"""

import json
import os
import re
from typing import AsyncGenerator

from openai import AsyncOpenAI

PRICING_SYSTEM_PROMPT = """You are Zara, the Pricing Strategist at CreativeOps Studio.
You cross-check the proposed budget against Scottish market benchmarks. You flag underpricing, find upsell opportunities, and are hyper-focused on margin.

Before your JSON output, write 2-3 sentences narrating your review. Be analytical and commercial.
Example:
[Thinking: James anchored this at £12k, which is fine, but we're leaving money on the table. The client is a well-funded Series A startup; they can afford £15k if we bundle in the social media templates...]

Then return ONLY valid JSON (no markdown fences):
{
  "margin_health": "poor|fair|good|excellent",
  "underpriced_warning": "true|false",
  "suggested_upsells": [
    {"item": "...", "price": "£X"}
  ],
  "negotiation_script": "Here is what to say if they try to cut 20%...",
  "final_recommended_price": "£XX,XXX"
}"""

async def run_pricing_agent(
    proposal_text: str,
    research_output: dict,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    yield "\n💭 [Zara] Crunching the numbers. Let's see if we're leaving money on the table...\n"

    user_message = f"""Review the proposal pricing against the market benchmarks.

## Market Benchmarks (from Research)
{json.dumps(research_output.get("budget_benchmarks", {}), indent=2)}

## Current Proposal
{proposal_text}

Provide your short narration, then the required JSON output:"""

    messages = [
        {"role": "system", "content": PRICING_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.3,
        max_tokens=1500,
    )

    raw_output = response.choices[0].message.content or ""

    lines = raw_output.strip().split("\n")
    narration_lines = []
    json_lines = []
    in_json = False

    for line in lines:
        if not in_json and line.strip().startswith("{"):
            in_json = True
        if in_json:
            json_lines.append(line)
        else:
            narration_lines.append(line)

    narration = "\n".join(narration_lines).strip()
    if narration:
        for sentence in narration.split("."):
            s = sentence.strip()
            if s:
                yield f"💭 [Zara] {s}.\n"

    json_text = "\n".join(json_lines).strip()

    # Clean up markdown code blocks if any
    json_match = re.search(r'\{[\s\S]*\}', json_text)
    if json_match:
        json_text = json_match.group(0)

    try:
        pricing_data = json.loads(json_text)
    except json.JSONDecodeError:
        pricing_data = {
            "margin_health": "unknown",
            "underpriced_warning": "false",
            "suggested_upsells": [],
            "negotiation_script": "Manually verify pricing.",
            "final_recommended_price": "Unknown"
        }

    yield f"\n💭 [Zara] Pricing strategy complete. Margin health looks {pricing_data.get('margin_health')}.\n"
    yield f"\n__PRICING_OUTPUT__:{json.dumps(pricing_data)}"
