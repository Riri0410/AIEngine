"""
Research Agent — Agent 1 of the CreativeOps pipeline.

Responsibilities:
- Accepts a raw client brief string
- Uses OpenAI function calling to invoke web_search tool (mocked)
- Pulls relevant past-client context (simulated RAG)
- Streams "thinking" tokens in real time
- Returns structured ResearchOutput dict
"""

import json
import os
from typing import AsyncGenerator

from openai import AsyncOpenAI

from tools.web_search import WEB_SEARCH_TOOL_SCHEMA, handle_tool_call
from mock_data.past_clients import get_relevant_clients, format_client_context

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ResearchOutput = dict  # keys: client_summary, competitors, market_insights, budget_benchmarks

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

RESEARCH_SYSTEM_PROMPT = """You are a senior research analyst at a Scottish creative agency.
Your job is to deeply research a new client brief to prepare the proposal team.

You have access to a web_search tool that retrieves real Scottish creative industry data.
You MUST call web_search at least 3 times to gather:
1. Industry/market overview relevant to the client's sector
2. Competitor landscape (Edinburgh or Glasgow agencies, whichever is relevant)
3. Budget benchmarks and day rates for this type of project

After your searches, synthesise your findings into a structured JSON research report.

Output ONLY valid JSON in this exact schema (no markdown fences, just raw JSON):
{
  "client_summary": "2–3 sentence overview of the client, their sector, and what they need",
  "industry_context": "Key market facts, size, growth trends relevant to this brief",
  "competitors": [
    {"name": "Agency Name", "strengths": "...", "avg_project_value": "£X–£Y", "why_client_might_consider": "..."}
  ],
  "market_insights": "Key insights about the client's sector that should shape our proposal",
  "budget_benchmarks": {
    "market_low": 0,
    "market_mid": 0,
    "market_high": 0,
    "recommended_budget": 0,
    "notes": "Rationale for recommendation"
  },
  "strategic_recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"]
}"""

# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

async def run_research_agent(
    brief: str,
    client: AsyncOpenAI | None = None,
) -> AsyncGenerator[str, None]:
    """
    Streams research agent output token-by-token.

    Yields:
        str chunks — either streaming text tokens or a final sentinel JSON blob.

    The final yielded item is a JSON string prefixed with "__RESEARCH_OUTPUT__:"
    which the orchestrator captures as the structured result.
    """
    if client is None:
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

    # Augment brief with past-client memory
    relevant_clients = get_relevant_clients(brief)
    past_context = format_client_context(relevant_clients)

    user_message = f"""New client brief received:

---
{brief}
---

{past_context}

Research this brief thoroughly using the web_search tool, then return your structured JSON report."""

    messages = [
        {"role": "system", "content": RESEARCH_SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    # We'll accumulate tool calls across the agentic loop
    tool_call_rounds = 0
    MAX_TOOL_ROUNDS = 6  # Safety limit

    while tool_call_rounds < MAX_TOOL_ROUNDS:
        # Non-streaming call when we expect tool use (tool calls aren't streamable cleanly)
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            tools=[WEB_SEARCH_TOOL_SCHEMA],
            tool_choice="auto",
            temperature=0.3,
        )

        choice = response.choices[0]

        # If the model wants to call tools
        if choice.finish_reason == "tool_calls":
            tool_calls = choice.message.tool_calls
            messages.append(choice.message)  # append assistant message with tool_calls

            for tc in tool_calls:
                tool_name = tc.function.name
                tool_args = tc.function.arguments

                # Yield a status line so the UI shows "thinking"
                yield f"\n🔎 Searching: {json.loads(tool_args).get('query', tool_name)}...\n"

                result_str = handle_tool_call(tool_name, tool_args)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

            tool_call_rounds += 1
            continue  # Loop back for next model response

        # Model finished — stream the final response
        if choice.finish_reason in ("stop", "length"):
            final_content = choice.message.content or ""

            # Stream it character-by-character for demo effect
            # (in production you'd use stream=True from the start)
            chunk_size = 8
            for i in range(0, len(final_content), chunk_size):
                yield final_content[i : i + chunk_size]

            # Now parse and emit the structured result
            research_data = _parse_research_output(final_content)
            yield f"\n__RESEARCH_OUTPUT__:{json.dumps(research_data)}"
            return

        # Unexpected finish reason
        yield f"\n[Research agent stopped: {choice.finish_reason}]\n"
        return

    yield "\n[Research agent hit tool call limit — returning partial data]\n"


def _parse_research_output(raw: str) -> ResearchOutput:
    """
    Parse the model's JSON output into a structured dict.
    Handles cases where the model wraps JSON in markdown fences.
    """
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # Drop first and last fence lines
        inner = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        text = inner.strip()

    try:
        data = json.loads(text)
        return data
    except json.JSONDecodeError:
        # Fallback: return raw text wrapped in a minimal structure
        return {
            "client_summary": "Research completed — see raw output.",
            "industry_context": raw[:500],
            "competitors": [],
            "market_insights": "",
            "budget_benchmarks": {
                "market_low": 0,
                "market_mid": 0,
                "market_high": 0,
                "recommended_budget": 0,
                "notes": "Could not parse structured benchmarks.",
            },
            "strategic_recommendations": [],
            "_raw": raw,
        }
