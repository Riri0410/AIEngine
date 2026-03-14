"""
Proposal Agent — James McAllister, Senior Account Director
Agent 2: Writes the client-facing proposal.
"""

import os
from typing import AsyncGenerator

from openai import AsyncOpenAI

JAMES_SYSTEM_PROMPT = """You are James McAllister, Senior Account Director at CreativeOps Studio.
You write compelling proposals that win business. You are confident, persuasive, commercially sharp.

ALWAYS prefix every "[James]" thinking line with "[James]".

Before writing the proposal, output 2-3 lines starting with "[James]" explaining:
1. The key strategic insight you're leading with (from Maya's research)
2. How you're positioning the budget
3. One risk you're consciously managing

Then write the FULL proposal with ALL sections:

---
# [Client Name] × CreativeOps Studio — Project Proposal

## Executive Summary
(2–3 paragraphs. What we understand, why it matters, what we'll deliver.)

## Client Overview
(Client background, sector position, current challenge.)

## Proposed Scope of Work
(Bulleted deliverables grouped by phase. Be specific — name formats, quantities, tools.)

## Project Timeline
| Week | Phase | Milestones | Deliverables |
|------|-------|------------|--------------|

## Budget Breakdown
| Item | Rate | Days/Units | Subtotal |
|------|------|------------|----------|
**Total: £XX,XXX**

## Why Choose Us
(3–5 bullets. Reference Scottish market knowledge, past results, team access.)

## Next Steps
(Numbered. Step 1 = approval. Step 2 = contract. Step 3 = kickoff date.)
---

All prices in GBP. Budget ±10% of stated figure. Timeline 4–8 weeks unless brief specifies."""

JAMES_FRINGE_SYSTEM_PROMPT = """You are James McAllister, Senior Account Director at CreativeOps Studio.
This is an Edinburgh Fringe act. Write a CAMPAIGN proposal, not a standard agency brief.

ALWAYS prefix thinking lines with "[James]".

Before writing, output 2-3 "[James]" lines about your Fringe-specific strategy.

Then write:

---
# [Act Name] × CreativeOps Studio — Fringe Marketing Campaign

## Executive Summary
(The story: what's the show, why audiences should care, what we're going to do.)

## About the Act
(Background, genre, previous shows if any, what makes this one different.)

## Campaign Strategy
(Ticket sales funnel: Awareness → Consideration → Purchase. Platform mix rationale.)

## Campaign Deliverables
**Phase 1 — Pre-Launch (Weeks 1–2):** Press release, social profiles setup, email list building
**Phase 2 — Launch (Weeks 3–4):** Paid social, influencer/reviewer outreach, content creation
**Phase 3 — Fringe Run (Weeks 5–8):** Live coverage, reviews amplification, last-minute sales
**Phase 4 — Post-Fringe:** Archive content, audience nurturing, touring announcement

## Timeline
| Week | Phase | Activity | Deliverables |

## Budget Breakdown
| Item | Rate | Days/Units | Subtotal |
(Include: Strategy, Content Creation, Paid Social Ads, PR, Email Setup, Photography, Management)
**Total: £X,XXX**

## Why We Get Fringe
(Reference our Fringe Forward 2024 campaign — 91% ticket sell-through, 7.2k followers gained.)

## Next Steps
---"""


async def run_proposal_agent(
    brief: str,
    research_output: dict,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    is_fringe = research_output.get("is_fringe", False)
    system_prompt = JAMES_FRINGE_SYSTEM_PROMPT if is_fringe else JAMES_SYSTEM_PROMPT
    research_context = _format_research_for_prompt(research_output)

    # James's pre-stream narration (these come before proposal text)
    if is_fringe:
        yield "[James] Fringe brief — not writing a standard agency proposal. This is a ticket-sales campaign with a storytelling angle.\n"
        yield "[James] Budget is arts-scale. Structuring around the 8-week window to opening night.\n"
    else:
        stated = research_output.get("stated_budget", 0)
        mid = research_output.get("budget_benchmarks", {}).get("market_mid", 0)
        if stated and mid and stated < mid * 0.8:
            yield f"[James] Maya's right — their budget (£{stated:,}) is below market mid (£{mid:,}). I'm going to anchor deliverables to outcomes, not hours, and justify every line item.\n"
        else:
            yield "[James] Maya's research is solid. Leading with the competitive positioning gap she identified.\n"
        yield "[James] Going to anchor 5% below their stated figure to give them negotiating room upward.\n"

    user_message = f"""Write a complete proposal based on this brief and research.

## Original Brief
{brief}

## Research (from Maya)
{research_context}

Rules:
- Agency name: CreativeOps Studio
- All prices in GBP (£)
- Match stated budget ±10%
- Realistic timeline
{"- FRINGE ACT: Use the arts campaign structure. Focus on ticket sales." if is_fringe else ""}

Write the complete proposal now:"""

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

    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content

    yield "\n[James] ✅ Proposal written. Sending to Priya for creative review.\n"


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
        for k in ("market_low", "market_mid", "market_high", "recommended_budget"):
            v = benchmarks.get(k)
            if isinstance(v, (int, float)) and v:
                lines.append(f"  - {k.replace('_', ' ').title()}: £{v:,}")
        if benchmarks.get("notes"):
            lines.append(f"  - Notes: {benchmarks['notes']}")
        lines.append("")

    competitors = research.get("competitors", [])
    if competitors:
        lines.append("**Competitor Landscape:**")
        for c in competitors[:4]:
            name = c.get("name", "")
            strength = c.get("strengths", c.get("strength", ""))
            weakness = c.get("weakness", c.get("weaknesses", ""))
            avg = c.get("avg_project_value", c.get("avg_project", ""))
            lines.append(f"  - {name}: {strength} (avg: {avg}){' | Weakness: ' + weakness if weakness else ''}")
        lines.append("")

    recs = research.get("strategic_recommendations", [])
    if recs:
        lines.append("**Strategic Recommendations from Maya:**")
        for r in recs:
            lines.append(f"  - {r}")

    return "\n".join(lines) if lines else "No structured research available."
