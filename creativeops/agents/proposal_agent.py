"""
Proposal Agent — Agent 2 of the CreativeOps pipeline.
Enhanced with agent voice narration and Fringe/arts mode.
"""

import os
from typing import AsyncGenerator

from openai import AsyncOpenAI

PROPOSAL_SYSTEM_PROMPT = """You are James, a Senior Account Director at CreativeOps Studio Edinburgh.
You write proposals that win business. You're strategic, warm, and specific — never generic.

Before you write each section, briefly narrate your reasoning in brackets like:
[Thinking: Setting budget at £X because competitor data shows Y...]
[Thinking: Emphasising local market knowledge because client is Edinburgh-based...]

Then write the actual section content.

Your proposals MUST include ALL sections in order:

---

# [Client Name] × CreativeOps Studio — Project Proposal

## Executive Summary
(2-3 paragraphs. What we understand, why it matters, what we'll deliver.)

## Client Overview
(Client sector, market position, current challenge.)

## Proposed Scope of Work
(Bulleted deliverables by phase. Specific formats, quantities, tools.)

## Project Timeline
| Week | Phase | Milestones | Deliverables |
|------|-------|------------|--------------|

## Budget Breakdown
| Item | Rate | Days/Units | Subtotal |
|------|------|------------|----------|
**Total: £XX,XXX**

## Why Choose Us
(3-5 bullets. Reference relevant past Scottish work, specific team strengths.)

## Next Steps
(Numbered. Step 1 = approval. Step 2 = contract. Step 3 = kickoff date.)

---
Do not add text outside these sections."""

FRINGE_PROPOSAL_SYSTEM_PROMPT = """You are James, Senior Account Director at CreativeOps Studio Edinburgh.
You've helped 12 Fringe acts sell out in the past 3 years. You know what works.

Before each section, briefly narrate your thinking:
[Thinking: This act needs press previews above everything else — that's 40% of Fringe ticket sales...]
[Thinking: Flyering budget is non-negotiable for spoken word — it's how you find the walk-up audience...]

Write a Fringe marketing campaign proposal with ALL sections:

---

# [Act Name] × CreativeOps Studio — Fringe 2025 Campaign Proposal

## Executive Summary
(What we understand about the act, the opportunity, and what we'll deliver.)

## Act Overview
(Genre, venue, show details, target audience, ticket targets.)

## Campaign Strategy
(Core positioning, key messages, primary channels for a Fringe act.)

## Proposed Scope of Work
Phase 1 — Pre-Fringe (Weeks 1-4): awareness building
Phase 2 — Fringe Week 1: launch push, press reviews
Phase 3 — Fringe Weeks 2-3: sell-out drive, word of mouth amplification

## Marketing Channels & Tactics
(Social media, press outreach, flyering strategy, email, listings, influencers)

## Timeline
| Week | Phase | Focus | Key Actions |
|------|-------|-------|-------------|

## Budget Breakdown
| Item | Cost | Notes |
|------|------|-------|
**Total: £X,XXX**

## Why CreativeOps for Fringe
(Specific Fringe experience, Edinburgh network, press contacts.)

## Next Steps
(Numbered, starting with approval call.)

---
All prices in GBP. Be specific about Fringe tactics — name real venues, real press contacts, real channels."""


async def run_proposal_agent(
    brief: str,
    research_output: dict,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    is_fringe = research_output.get("is_fringe_act", False)
    system_prompt = FRINGE_PROPOSAL_SYSTEM_PROMPT if is_fringe else PROPOSAL_SYSTEM_PROMPT

    research_context = _format_research_for_prompt(research_output)

    # Agent voice intro
    if is_fringe:
        yield "\n💭 [James] Fringe proposal — completely different approach to a standard agency pitch. Let me think about what actually sells shows...\n"
        competitors = research_output.get("competitors", [])
        if competitors:
            yield f"💭 [James] Key competitive insight: {competitors[0].get('strengths', '')} — we need to position against that.\n"
        yield "✍️ [James] Starting the proposal now...\n\n"
    else:
        budget = research_output.get("budget_benchmarks", {})
        rec = budget.get("recommended_budget", 0)
        if rec:
            yield f"\n💭 [James] Market data puts this at £{rec:,} recommended. I'll anchor there with room for the client to feel they're getting value.\n"
        recs = research_output.get("strategic_recommendations", [])
        if recs:
            yield f"💭 [James] Key angle: {recs[0]}\n"
        yield "✍️ [James] Writing the proposal now...\n\n"

    user_message = f"""Write a full project proposal based on this brief and research.

## Original Brief
{brief}

## Research Findings
{research_context}

Important:
- If brief mentions a specific budget, the breakdown MUST total to that amount (±10%).
- If no budget mentioned, use the recommended_budget from benchmarks.
- Agency name: "CreativeOps Studio" unless brief specifies otherwise.
- All monetary values in GBP (£).
- Narrate your thinking briefly before each section using [Thinking: ...] format.
- EXPLICITLY reference "Maya" (our Research Agent) by name when citing research data.
- INCLUDE a note at the end for Priya (the Critique Agent) formatted exactly as:
  [Thinking: Passing a note to Priya: I anchored deliberately based on Maya's data, please don't flag the budget as an error.]
- Be specific — name real Scottish/Edinburgh market context throughout.

Write the complete proposal:"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    stream = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.6,
        stream=True,
        max_tokens=3500,
    )

    buffer = ""
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            buffer += delta.content

            # Tag [Thinking: ...] lines as agent voice lines for frontend
            # Just yield them — the frontend will colour them differently
            yield delta.content


def _format_research_for_prompt(research: dict) -> str:
    lines = []

    if research.get("client_summary"):
        lines.append(f"**Client Summary:** {research['client_summary']}\n")
    if research.get("industry_context"):
        lines.append(f"**Industry Context:** {research['industry_context']}\n")
    if research.get("market_insights"):
        lines.append(f"**Market Insights:** {research['market_insights']}\n")

    benchmarks = research.get("budget_benchmarks", {})
    if benchmarks:
        lines.append("**Budget Benchmarks:**")
        for key in ["market_low", "market_mid", "market_high", "recommended_budget"]:
            val = benchmarks.get(key, "N/A")
            label = key.replace("_", " ").title()
            lines.append(f"  - {label}: £{val:,}" if isinstance(val, int) else f"  - {label}: {val}")
        if benchmarks.get("notes"):
            lines.append(f"  - Notes: {benchmarks['notes']}")
        lines.append("")

    competitors = research.get("competitors", [])
    if competitors:
        lines.append("**Competitor Landscape:**")
        for c in competitors[:4]:
            name = c.get("name", "Unknown")
            strengths = c.get("strengths", c.get("strength", ""))
            avg = c.get("avg_project_value", c.get("avg_project", ""))
            lines.append(f"  - {name}: {strengths} (avg: {avg})")
        lines.append("")

    recs = research.get("strategic_recommendations", [])
    if recs:
        lines.append("**Strategic Recommendations:**")
        for r in recs:
            lines.append(f"  - {r}")

    if research.get("is_fringe_act"):
        lines.append("\n**NOTE: This is a Fringe act. Prioritise press outreach, flyering, and social proof over generic digital marketing.**")

    return "\n".join(lines) if lines else "No structured research available."