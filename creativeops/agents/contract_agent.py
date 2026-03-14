"""
Contract Scout Agent — Liam Fraser
Reviews the brief and proposal for IP/payment/revision/scope risks.
Emits 💭 [Liam] voice lines and returns __CONTRACT_OUTPUT__: JSON.
"""

import json
import os
from typing import AsyncGenerator

from openai import AsyncOpenAI

LIAM_SYSTEM_PROMPT = """You are Liam Fraser, Contract & Scope Specialist at CreativeOps Studio.
You've seen every way a contract can hurt an agency — unpaid invoices, unlimited revisions,
unclear IP, and clients who disappear at final delivery.

ALWAYS prefix every line with "[Liam]".

Review the brief and proposal for:
1. IP ownership — who owns deliverables before/after payment?
2. Payment terms — is there a deposit, schedule, kill fee?
3. Revision rounds — are they capped?
4. Scope definition — are deliverables specific enough to prevent scope creep?
5. Timeline dependencies — are client response windows stated?

Write 3-4 "[Liam]" lines flagging the top risks, then output ONLY valid JSON (no markdown fences):
{
  "risk_level": "low|medium|high",
  "scope_risks": ["risk 1", "risk 2"],
  "ip_clarity": "clear|unclear|missing",
  "payment_terms_present": true,
  "revision_rounds_capped": false,
  "recommended_additions": ["addition to add to proposal", "..."],
  "contract_terms": {
    "payment_schedule": "50% upfront, 50% on delivery",
    "revision_rounds": "2 rounds included",
    "kill_fee": "25% of project value if cancelled after kickoff",
    "ip_transfer": "Full IP transfers to client on final payment",
    "timeline_dependencies": "Client to provide assets within 3 business days"
  },
  "priya_note": "One line to relay to Priya if she missed anything contract-related"
}"""


async def run_contract_agent(
    proposal_text: str,
    original_brief: str,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    yield "[Liam] Scanning brief and proposal for contractual risks. This is where agencies lose money.\n"

    user_message = f"""Review this brief and proposal for contract and scope risks.

## Brief
{original_brief[:600]}

## Proposal
{proposal_text[:3000]}

Write [Liam] commentary (3-4 lines), then output the JSON:"""

    messages = [
        {"role": "system", "content": LIAM_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2,
        max_tokens=1200,
    )

    raw = response.choices[0].message.content or ""

    chunk_size = 10
    for i in range(0, len(raw), chunk_size):
        yield raw[i: i + chunk_size]

    contract_data = _parse_output(raw)
    risk = contract_data.get("risk_level", "medium")
    yield f"\n[Liam] ✅ Contract analysis done. Risk level: {risk.upper()}.\n"
    yield f"\n__CONTRACT_OUTPUT__:{json.dumps(contract_data)}"


def _parse_output(raw: str) -> dict:
    text = raw.strip()
    json_start = text.find('{')
    if json_start >= 0:
        try:
            return json.loads(text[json_start:])
        except json.JSONDecodeError:
            pass
    return {
        "risk_level": "medium",
        "scope_risks": ["Scope not precisely defined — risk of expansion"],
        "ip_clarity": "unclear",
        "payment_terms_present": False,
        "revision_rounds_capped": False,
        "recommended_additions": [
            "Add payment schedule (50% upfront, 50% on delivery)",
            "Cap revision rounds to 2 per phase",
            "State client response SLA (3 business days)",
        ],
        "contract_terms": {
            "payment_schedule": "50% upfront, 50% on final delivery",
            "revision_rounds": "2 rounds of consolidated revisions per phase",
            "kill_fee": "25% of project value if cancelled after kickoff",
            "ip_transfer": "Full IP transfers to client upon receipt of final payment",
            "timeline_dependencies": "Client to provide all source assets within 3 business days of kickoff",
        },
        "priya_note": "Proposal lacks explicit payment terms and revision limits — flag in next revision.",
    }
