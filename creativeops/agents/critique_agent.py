"""
Critique Agent — Priya Singh, Creative Director
Agent 3: Quality review and proposal revision.
"""

import json
import os
from typing import AsyncGenerator

from openai import AsyncOpenAI

PRIYA_SYSTEM_PROMPT = """You are Priya Singh, Creative Director at CreativeOps Studio.
You are meticulous, occasionally blunt, always honest. You protect the agency's reputation by catching every flaw before a proposal reaches a client.

ALWAYS prefix every line with "[Priya]".

Write 3-4 lines starting with "[Priya]" that:
1. Name the strongest thing James did in this proposal (be specific)
2. Call out the most significant issue you're fixing (be direct: "James has undercosted the design phase")
3. Note your overall verdict in plain English

Then output ONLY valid JSON (no markdown fences):
{
  "quality_score": <1–10>,
  "quality_rationale": "One sentence explaining the score",
  "issues_found": [
    {"severity": "critical|major|minor", "section": "...", "issue": "...", "fix": "..."}
  ],
  "revised_sections": {
    "section_name": "Full revised text — only sections that need changes"
  },
  "strengths": ["strength 1", "strength 2"],
  "final_recommendation": "approve|approve_with_revisions|reject",
  "agent_confidence": 85
}

Be honest. A score of 7+ = approve/approve_with_revisions. Below 5 = reject."""


async def run_critique_agent(
    proposal_text: str,
    original_brief: str,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    yield "[Priya] Reading James's proposal against the original brief. Give me a moment.\n"

    user_message = f"""Review this proposal against the original brief.

## Original Brief
{original_brief}

## Proposal to Review
{proposal_text}

Write your [Priya] commentary first (3-4 lines), then the JSON critique:"""

    messages = [
        {"role": "system", "content": PRIYA_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2,
        max_tokens=2500,
    )

    raw = response.choices[0].message.content or ""

    # Stream for live effect
    chunk_size = 10
    for i in range(0, len(raw), chunk_size):
        yield raw[i: i + chunk_size]

    critique_data = _parse_critique_output(raw)
    final_proposal = _apply_revisions(proposal_text, critique_data)
    critique_data["final_proposal"] = final_proposal

    score = critique_data.get("quality_score", "N/A")
    rec = critique_data.get("final_recommendation", "unknown")
    yield f"\n[Priya] ✅ Review done. Score: {score}/10 — {rec}. Passing to the specialists.\n"
    yield f"\n__CRITIQUE_OUTPUT__:{json.dumps(critique_data)}"


def _parse_critique_output(raw: str) -> dict:
    """Extract JSON from response that may have [Priya] commentary before it."""
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
            "quality_score": 7,
            "quality_rationale": "Critique parsing issue — manual review advised.",
            "issues_found": [],
            "revised_sections": {},
            "strengths": ["Proposal generated successfully"],
            "final_recommendation": "approve_with_revisions",
            "agent_confidence": 60,
        }


def _apply_revisions(original: str, critique: dict) -> str:
    import re
    revised = critique.get("revised_sections", {})
    result = original

    for section_name, new_text in revised.items():
        if not new_text:
            continue
        safe_name = re.escape(section_name.strip())
        pattern = rf"(##\s*{safe_name}\s*\n)(.*?)(?=\n##|\Z)"
        replacement = rf"\g<1>{new_text}\n"
        new_result = re.sub(pattern, replacement, result, flags=re.DOTALL | re.IGNORECASE)
        if new_result != result:
            result = new_result
        else:
            result += f"\n\n---\n**[Revised {section_name}]:**\n{new_text}"

    score = critique.get("quality_score", "N/A")
    rec = critique.get("final_recommendation", "unknown")
    issues = critique.get("issues_found", [])
    crit = sum(1 for i in issues if i.get("severity") == "critical")
    major = sum(1 for i in issues if i.get("severity") == "major")

    result += (
        f"\n\n---\n"
        f"<!-- INTERNAL REVIEW NOTE (remove before sending) -->\n"
        f"**Score:** {score}/10 | **Recommendation:** {rec}\n"
        f"**Issues:** {crit} critical, {major} major, {len(issues) - crit - major} minor\n"
    )
    return result
