"""
Contract Agent — Agent 4 of the CreativeOps pipeline.
"""

import json
import os
import re
from typing import AsyncGenerator

from openai import AsyncOpenAI

CONTRACT_SYSTEM_PROMPT = """You are Liam, the Contract Scout at CreativeOps Studio. 
You review the brief and proposal for IP, payment, revision, and scope risks. You are sharp, legally minded, and a bit cynical about scope creep.

Before your JSON output, write 2-3 sentences narrating your review. Be direct and concise.
Example:
[Thinking: This scope is way too loose on the 'branding iteration' phase. I'm flagging that we need a hard cap on 3 rounds of revisions, otherwise this will bleed us dry...]

Then return ONLY valid JSON (no markdown fences):
{
  "risk_score": <integer 1-10, higher is riskier>,
  "ip_ownership_risks": "String description",
  "payment_term_flags": "String description",
  "revision_scope_risks": "String description",
  "recommended_clauses": [
    "clause 1", "clause 2"
  ]
}"""

async def run_contract_agent(
    brief: str,
    proposal_text: str,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    yield "\n💭 [Liam] Reviewing the proposal for legal and scope risks...\n"

    user_message = f"""Review the brief and proposal for any contract/scope risks.

## Original Brief
{brief}

## Current Proposal
{proposal_text}

Provide your short narration, then the required JSON output:"""

    messages = [
        {"role": "system", "content": CONTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2,
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
                yield f"💭 [Liam] {s}.\n"

    json_text = "\n".join(json_lines).strip()
    
    # Clean up markdown code blocks if any
    json_match = re.search(r'\{[\s\S]*\}', json_text)
    if json_match:
        json_text = json_match.group(0)

    try:
        contract_data = json.loads(json_text)
    except json.JSONDecodeError:
        contract_data = {
            "risk_score": 5,
            "ip_ownership_risks": "Could not parse review.",
            "payment_term_flags": "Review manually.",
            "revision_scope_risks": "Review manually.",
            "recommended_clauses": []
        }

    yield f"\n💭 [Liam] Contract risk assessed. Risk score: {contract_data.get('risk_score')}/10.\n"
    yield f"__CONTRACT_OUTPUT__:{json.dumps(contract_data)}"
