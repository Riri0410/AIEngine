"""
Critique Agent — Agent 3 of the CreativeOps pipeline.

Responsibilities:
- Reviews the generated proposal for quality, gaps, and realism
- Returns a structured critique with issues, quality score, and revised sections
- Applies revisions back to the proposal to produce a final polished version
- Streams its review commentary, then yields a structured JSON result
"""

import json
import os
from typing import AsyncGenerator

from openai import AsyncOpenAI

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

CRITIQUE_SYSTEM_PROMPT = """You are a meticulous Senior Creative Director reviewing a project proposal
before it goes to a client. You have 15 years of experience at Scottish and UK creative agencies.

Your review checks for:
1. **Completeness** — Are all required sections present? (Executive Summary, Client Overview,
   Scope, Timeline, Budget, Why Choose Us, Next Steps)
2. **Budget realism** — Does the budget add up correctly? Are day rates in the UK market range?
   Are there any missing cost items (e.g., software licences, print costs, ad spend)?
3. **Timeline realism** — Is the timeline achievable for the scope described? Are dependencies clear?
4. **Scope gaps** — Are there deliverables implied by the brief that aren't in the scope?
5. **Tone & professionalism** — Is it written in professional British English? Appropriate for the client?
6. **Competitive positioning** — Does the proposal differentiate the agency clearly?

Return ONLY valid JSON (no markdown fences) in this exact schema:
{
  "quality_score": <integer 1–10>,
  "quality_rationale": "One sentence explaining the score",
  "issues_found": [
    {
      "severity": "critical|major|minor",
      "section": "Section name",
      "issue": "Description of the problem",
      "fix": "Specific recommended fix"
    }
  ],
  "revised_sections": {
    "section_name": "Full revised text for this section (only include sections that need changes)"
  },
  "strengths": ["strength 1", "strength 2"],
  "final_recommendation": "approve|approve_with_revisions|reject"
}

Be honest but constructive. A score of 7+ means approve_with_revisions or approve.
A score below 5 means reject."""

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

async def run_critique_agent(
    proposal_text: str,
    original_brief: str,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    """
    Streams critique commentary, then yields a structured JSON result.

    Yields:
        str chunks of the critique narrative.

    The final yielded item is prefixed with "__CRITIQUE_OUTPUT__:" followed by
    a JSON string containing the structured CritiqueOutput.
    """
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    user_message = f"""Review the following project proposal against the original client brief.

## Original Brief
{original_brief}

## Proposal to Review
{proposal_text}

Produce your structured critique JSON now:"""

    messages = [
        {"role": "system", "content": CRITIQUE_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # Non-streaming for structured JSON output (more reliable)
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2,  # Low temp for consistent structured output
        max_tokens=2000,
    )

    raw_critique = response.choices[0].message.content or ""

    # Stream the raw critique text for demo effect
    chunk_size = 12
    for i in range(0, len(raw_critique), chunk_size):
        yield raw_critique[i : i + chunk_size]

    # Parse and emit structured result
    critique_data = _parse_critique_output(raw_critique)

    # Apply revisions to produce final proposal
    final_proposal = _apply_revisions(proposal_text, critique_data)
    critique_data["final_proposal"] = final_proposal

    yield f"\n__CRITIQUE_OUTPUT__:{json.dumps(critique_data)}"


def _parse_critique_output(raw: str) -> dict:
    """Parse model JSON output, handling markdown fences."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = inner.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "quality_score": 6,
            "quality_rationale": "Critique parsing failed — manual review recommended.",
            "issues_found": [
                {
                    "severity": "minor",
                    "section": "General",
                    "issue": "Could not parse structured critique output.",
                    "fix": "Review proposal manually.",
                }
            ],
            "revised_sections": {},
            "strengths": ["Proposal generated successfully"],
            "final_recommendation": "approve_with_revisions",
            "_raw": raw,
        }


def _apply_revisions(original_proposal: str, critique: dict) -> str:
    """
    Apply revised sections from the critique back to the original proposal.
    Returns the final polished proposal text.
    """
    revised_sections: dict = critique.get("revised_sections", {})

    if not revised_sections:
        return original_proposal

    result = original_proposal

    for section_name, new_text in revised_sections.items():
        if not new_text:
            continue

        # Try to find the section header in the proposal and replace the block
        # Look for markdown ## headers matching the section name
        import re
        # Normalise section name for matching
        safe_name = re.escape(section_name.strip())
        # Pattern: match ## Section Name\n... up to the next ## or end of string
        pattern = rf"(##\s*{safe_name}\s*\n)(.*?)(?=\n##|\Z)"
        replacement = rf"\g<1>{new_text}\n"
        new_result = re.sub(pattern, replacement, result, flags=re.DOTALL | re.IGNORECASE)

        if new_result != result:
            result = new_result
        else:
            # If we couldn't find the section, append a note
            result += f"\n\n---\n**[Revised {section_name}]:**\n{new_text}"

    # Append critique summary as an internal review note (stripped before client send)
    score = critique.get("quality_score", "N/A")
    recommendation = critique.get("final_recommendation", "unknown")
    issues = critique.get("issues_found", [])
    critical_count = sum(1 for i in issues if i.get("severity") == "critical")
    major_count = sum(1 for i in issues if i.get("severity") == "major")

    review_note = (
        f"\n\n---\n"
        f"<!-- INTERNAL REVIEW NOTE (remove before sending) -->\n"
        f"**Quality Score:** {score}/10 | **Recommendation:** {recommendation}\n"
        f"**Issues:** {critical_count} critical, {major_count} major, "
        f"{len(issues) - critical_count - major_count} minor\n"
    )

    if issues:
        review_note += "**Issues to address:**\n"
        for issue in issues:
            sev = issue.get("severity", "").upper()
            section = issue.get("section", "")
            desc = issue.get("issue", "")
            fix = issue.get("fix", "")
            review_note += f"- [{sev}] {section}: {desc} → {fix}\n"

    return result + review_note
