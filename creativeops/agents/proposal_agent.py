"""
Proposal Agent — Agent 2 of the CreativeOps pipeline.

Responsibilities:
- Accepts the original client brief + structured ResearchOutput
- Generates a full, client-ready project proposal
- Streams output token-by-token via the OpenAI streaming API
- Returns the complete proposal text for the Critique Agent
"""

import os
from typing import AsyncGenerator

from openai import AsyncOpenAI

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

PROPOSAL_SYSTEM_PROMPT = """You are a Senior Account Director at a Scottish creative agency.
You write compelling, professional project proposals that win business.

Your proposals are:
- Specific to the client's industry and Scottish market context
- Grounded in realistic timelines and budgets (not over-promising)
- Written in warm, confident, professional British English
- Structured to guide the client through scope, timeline, and investment clearly

You MUST produce a proposal with ALL of the following sections, in order:

---

# [Client Name] × [Agency Name] — Project Proposal

## Executive Summary
(2–3 paragraphs. What we understand about the client, why this project matters, and what we'll deliver.)

## Client Overview
(What we know about the client, their sector, position in market, and current challenge.)

## Proposed Scope of Work
(Bulleted list of all deliverables, grouped by phase. Be specific — name actual formats, quantities, tools.)

## Project Timeline
(4-week breakdown with milestones. Use a table or clear week-by-week structure.)

| Week | Phase | Milestones | Deliverables |
|------|-------|------------|--------------|
| 1    | ...   | ...        | ...          |

## Budget Breakdown
(Itemised budget. Each line item must have: item name, day rate or fixed price, estimated days, subtotal.
Total must roughly match the client's stated budget. If no budget was given, use the market benchmark.)

| Item | Rate | Days/Units | Subtotal |
|------|------|------------|----------|

**Total: £XX,XXX**

## Why Choose Us
(3–5 bullet points. Reference relevant past experience, Scottish market knowledge, team strengths.)

## Next Steps
(Clear numbered list. Step 1 = client approval. Step 2 = contract. Step 3 = kickoff call date suggestion.)

---

Do not add any text outside of these sections. Do not include disclaimers or meta-commentary."""

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

async def run_proposal_agent(
    brief: str,
    research_output: dict,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    """
    Streams the proposal token-by-token.

    Yields:
        str chunks from the streaming OpenAI response.

    The final complete proposal text is accumulated by the orchestrator
    by joining all yielded chunks.
    """
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Build a rich context message from research output
    research_context = _format_research_for_prompt(research_output)

    user_message = f"""Write a full project proposal based on the following brief and research.

## Original Client Brief
{brief}

## Research Findings
{research_context}

Important:
- If the brief mentions a specific budget, the budget breakdown MUST total to that amount (±10%).
- If no budget is mentioned, use the recommended_budget from the research benchmarks.
- The agency name to use is "CreativeOps Studio" — unless the brief specifies otherwise.
- All monetary values in GBP (£).
- Timeline should be realistic given the scope, typically 4–8 weeks.

Now write the complete proposal:"""

    messages = [
        {"role": "system", "content": PROPOSAL_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # Stream tokens
    stream = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.6,
        stream=True,
        max_tokens=3000,
    )

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def _format_research_for_prompt(research: dict) -> str:
    """Convert structured research output into a readable prompt section."""
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
        lines.append(f"  - Market low: £{benchmarks.get('market_low', 'N/A'):,}" if isinstance(benchmarks.get('market_low'), int) else f"  - Market low: {benchmarks.get('market_low', 'N/A')}")
        lines.append(f"  - Market mid: £{benchmarks.get('market_mid', 'N/A'):,}" if isinstance(benchmarks.get('market_mid'), int) else f"  - Market mid: {benchmarks.get('market_mid', 'N/A')}")
        lines.append(f"  - Market high: £{benchmarks.get('market_high', 'N/A'):,}" if isinstance(benchmarks.get('market_high'), int) else f"  - Market high: {benchmarks.get('market_high', 'N/A')}")
        lines.append(f"  - Recommended: £{benchmarks.get('recommended_budget', 'N/A'):,}" if isinstance(benchmarks.get('recommended_budget'), int) else f"  - Recommended: {benchmarks.get('recommended_budget', 'N/A')}")
        if benchmarks.get("notes"):
            lines.append(f"  - Notes: {benchmarks['notes']}")
        lines.append("")

    competitors = research.get("competitors", [])
    if competitors:
        lines.append("**Competitor Landscape:**")
        for c in competitors[:4]:  # Cap at 4 to keep prompt lean
            name = c.get("name", "Unknown")
            strengths = c.get("strengths", c.get("strength", ""))
            avg = c.get("avg_project_value", c.get("avg_project", ""))
            lines.append(f"  - {name}: {strengths} (avg project: {avg})")
        lines.append("")

    recs = research.get("strategic_recommendations", [])
    if recs:
        lines.append("**Strategic Recommendations:**")
        for r in recs:
            lines.append(f"  - {r}")

    return "\n".join(lines) if lines else "No structured research available."
