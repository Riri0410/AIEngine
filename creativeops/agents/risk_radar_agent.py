"""
Risk Radar Agent — Riley O'Brien, Project Risk Specialist
Agent 6: Reads the brief for red flags and adds a risk register to the proposal.

Spots the things everyone else misses: vague scope, unrealistic timelines,
missing approval processes, client dependency risks.
"""

import json
import os
from typing import AsyncGenerator

from openai import AsyncOpenAI

RILEY_SYSTEM_PROMPT = """You are Riley O'Brien, Project Risk Specialist at CreativeOps Studio.
You've seen every way a project can go wrong — late assets, scope creep, stakeholder conflict,
disappearing clients, budget surprises. You protect the team before a project starts.

ALWAYS prefix every line with "[Riley]".

Read the brief AND the proposal for:
1. Vague scope (deliverables that could expand infinitely)
2. Timeline risks (is there enough time? are client dependencies stated?)
3. Client risks (signs of a difficult client, unclear decision-making, multiple stakeholders)
4. Commercial risks (kill fee missing? IP unclear? Unlimited revisions?)
5. Delivery risks (third-party dependencies, technical risks)

Write 3-4 "[Riley]" lines flagging the top risks, then output ONLY valid JSON:
{
  "overall_risk_level": "low|medium|high|critical",
  "risk_register": [
    {
      "risk_id": "R01",
      "category": "scope|timeline|client|commercial|delivery",
      "description": "Specific risk description",
      "likelihood": "low|medium|high",
      "impact": "low|medium|high",
      "mitigation": "Specific action to mitigate this risk",
      "proposal_addition": "Text to add to the proposal to protect us"
    }
  ],
  "missing_from_brief": ["Thing 1 the client hasn't specified that we need to know", "Thing 2"],
  "questions_to_ask": ["Question to ask client before signing", "Another question"],
  "go_no_go": "go|proceed_with_caution|no_go",
  "go_no_go_rationale": "One sentence",
  "agent_confidence": 88
}"""


async def run_risk_radar_agent(
    brief: str,
    proposal_text: str,
    critique_output: dict,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    yield "[Riley] Running risk scan on the brief and proposal. Looking for what everyone else missed.\n"

    # Check if critique already flagged issues
    issues = critique_output.get("issues_found", [])
    critical_count = sum(1 for i in issues if i.get("severity") == "critical")
    if critical_count > 0:
        yield f"[Riley] Priya flagged {critical_count} critical issues — I'll cross-reference those against my risk scan.\n"

    user_message = f"""Scan this brief and proposal for project risks.

## Original Brief
{brief}

## Proposal
{proposal_text[:3000]}

## Issues already flagged by Priya
{json.dumps(issues[:5], indent=2)}

Write 3-4 [Riley] lines about the top risks, then output the JSON risk register:"""

    messages = [
        {"role": "system", "content": RILEY_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2,
        max_tokens=1600,
    )

    raw = response.choices[0].message.content or ""

    chunk_size = 10
    for i in range(0, len(raw), chunk_size):
        yield raw[i: i + chunk_size]

    riley_data = _parse_riley_output(raw)
    risk_level = riley_data.get("overall_risk_level", "medium")
    go_no_go = riley_data.get("go_no_go", "proceed_with_caution")
    risks_count = len(riley_data.get("risk_register", []))
    yield f"\n[Riley] ✅ Risk scan complete. Level: {risk_level.upper()}. {risks_count} risks identified. Go/No-go: {go_no_go.upper()}.\n"
    yield f"\n__RILEY_OUTPUT__:{json.dumps(riley_data)}"


def _parse_riley_output(raw: str) -> dict:
    text = raw.strip()
    json_start = text.find('{')
    if json_start >= 0:
        try:
            return json.loads(text[json_start:])
        except json.JSONDecodeError:
            pass
    return {
        "overall_risk_level": "medium",
        "risk_register": [
            {
                "risk_id": "R01",
                "category": "scope",
                "description": "Deliverables not fully specified — could lead to scope creep",
                "likelihood": "medium",
                "impact": "medium",
                "mitigation": "Add detailed scope definition to contract",
                "proposal_addition": "All deliverables as listed. Additional work will be quoted separately."
            }
        ],
        "missing_from_brief": ["Approval process not specified", "Asset provision timeline unclear"],
        "questions_to_ask": ["Who is the single decision-maker for approvals?", "When will you provide existing brand assets?"],
        "go_no_go": "proceed_with_caution",
        "go_no_go_rationale": "Standard risks — manageable with clear contract.",
        "agent_confidence": 55,
    }
