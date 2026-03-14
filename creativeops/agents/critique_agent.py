"""
Critique Agent — Agent 3 of the CreativeOps pipeline.
Enhanced with agent voice narration.
"""

import json
import os
import re
from typing import AsyncGenerator

from openai import AsyncOpenAI

CRITIQUE_SYSTEM_PROMPT = """You are Priya, a meticulous Senior Creative Director at CreativeOps Studio.
15 years in Scottish and UK agencies. You review proposals before they go to clients.
You are honest, specific, and constructive — never vague.

Before your JSON output, write 2-3 sentences narrating your overall impression and
the most important thing you're fixing. Be direct — like you're talking to the team.

Then return ONLY valid JSON (no markdown fences):
{
  "quality_score": <integer 1-10>,
  "quality_rationale": "One sentence explaining the score",
  "issues_found": [
    {
      "severity": "critical|major|minor",
      "section": "Section name",
      "issue": "Description",
      "fix": "Specific fix"
    }
  ],
  "revised_sections": {
    "section_name": "Full revised text (only sections needing changes)"
  },
  "strengths": ["strength 1", "strength 2"],
  "priya_note_to_james": "String responding to James's approach",
  "final_recommendation": "approve|approve_with_revisions|reject"
}"""


async def run_critique_agent(
    proposal_text: str,
    original_brief: str,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Agent voice intro
    yield "\n💭 [Priya] Reading through the proposal now...\n"

    user_message = f"""Review this proposal against the original brief.

## Original Brief
{original_brief}

## Proposal to Review
{proposal_text}

Start with 2-3 sentences of honest narration (your overall impression, biggest fix needed),
then produce your structured critique JSON:"""

    messages = [
        {"role": "system", "content": CRITIQUE_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2,
        max_tokens=2000,
    )

    raw_critique = response.choices[0].message.content or ""

    # Split narration from JSON
    lines = raw_critique.strip().split("\n")
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

    # Stream narration as agent voice
    narration = "\n".join(narration_lines).strip()
    if narration:
        for sentence in narration.split("."):
            s = sentence.strip()
            if s:
                yield f"💭 [Priya] {s}.\n"

    json_text = "\n".join(json_lines).strip()

    # Stream the JSON for demo effect
    chunk_size = 12
    for i in range(0, len(json_text), chunk_size):
        yield json_text[i: i + chunk_size]

    critique_data = _parse_critique_output(raw_critique)
    final_proposal = _apply_revisions(proposal_text, critique_data)
    critique_data["final_proposal"] = final_proposal

    score = critique_data.get("quality_score", "N/A")
    rec = critique_data.get("final_recommendation", "unknown")
    yield f"\n💭 [Priya] Done. Score: {score}/10. Recommendation: {rec}. Sending to output.\n"
    yield f"\n__CRITIQUE_OUTPUT__:{json.dumps(critique_data)}"


def _parse_critique_output(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = inner.strip()

    json_match = re.search(r'\{[\s\S]*\}', text)
    if json_match:
        text = json_match.group(0)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "quality_score": 6,
            "quality_rationale": "Critique parsing failed — manual review recommended.",
            "issues_found": [{"severity": "minor", "section": "General",
                              "issue": "Could not parse structured critique.", "fix": "Review manually."}],
            "revised_sections": {},
            "strengths": ["Proposal generated successfully"],
            "priya_note_to_james": "Critique failed, check manually.",
            "final_recommendation": "approve_with_revisions",
            "_raw": raw,
        }


def _apply_revisions(original_proposal: str, critique: dict) -> str:
    revised_sections: dict = critique.get("revised_sections", {})
    if not revised_sections:
        return original_proposal

    result = original_proposal
    for section_name, new_text in revised_sections.items():
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
    return result + review_note