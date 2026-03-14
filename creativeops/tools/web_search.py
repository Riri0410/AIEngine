"""
Web Search Tool — CreativeOps AI

Live mode:  Uses Tavily API (set TAVILY_API_KEY env var).
Mock mode:  Falls back to hardcoded Scottish creative industry data when
            TAVILY_API_KEY is not set or tavily-python is not installed.

The tool schema exposed to OpenAI is the same in both modes — the research
agent doesn't need to know which backend is active.
"""

import json
import os
import re
from typing import Any

# ── Tavily client (optional dependency) ─────────────────────────────────────
try:
    from tavily import TavilyClient as _TavilyClient
    _TAVILY_IMPORTED = True
except ImportError:
    _TAVILY_IMPORTED = False


# ---------------------------------------------------------------------------
# Tool schema (OpenAI function-calling format)
# ---------------------------------------------------------------------------

WEB_SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for current information about a client's industry, "
            "Scottish creative agency competitors, market benchmarks, and pricing. "
            "Use specific, targeted queries for best results."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The search query. Be specific. Examples: "
                        "'Scottish music industry market size 2024', "
                        "'Edinburgh branding agency day rates', "
                        "'UK digital marketing campaign benchmarks'"
                    ),
                },
            },
            "required": ["query"],
        },
    },
}


# ---------------------------------------------------------------------------
# Real search — Tavily
# ---------------------------------------------------------------------------

def _real_search(query: str) -> dict[str, Any] | None:
    """
    Execute a live web search via Tavily.
    Returns structured result dict, or None if unavailable / error.
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key or not _TAVILY_IMPORTED:
        return None

    try:
        client = _TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            max_results=5,
            search_depth="advanced",
            include_answer=True,
            include_raw_content=False,
        )

        results = response.get("results", [])
        answer  = response.get("answer", "")

        sources = [
            {
                "title":   r.get("title", ""),
                "url":     r.get("url", ""),
                "snippet": r.get("content", "")[:500],
                "score":   round(r.get("score", 0), 3),
            }
            for r in results[:5]
        ]

        return {
            "query":   query,
            "answer":  answer,
            "sources": sources,
            "mode":    "live",
        }

    except Exception as exc:
        return {"query": query, "error": str(exc), "mode": "live_error"}


def _format_real_result(result: dict) -> str:
    """Format a Tavily result into readable text for the LLM."""
    lines = [f"## Web Search: {result['query']}\n"]

    if result.get("error"):
        lines.append(f"⚠️  Search error: {result['error']}\n")
        return "\n".join(lines)

    if result.get("answer"):
        lines.append(f"**Summary:** {result['answer']}\n")

    for i, src in enumerate(result.get("sources", []), 1):
        lines.append(f"### Source {i}: {src['title']}")
        lines.append(f"URL: {src['url']}")
        lines.append(src["snippet"])
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MOCK fallback data — kept for reference & offline use
# ---------------------------------------------------------------------------
# fmt: off
_MOCK_SEARCH_DATA: dict[str, dict[str, Any]] = {
    "scottish_creative_industry_overview": {
        "source": "Creative Scotland Annual Report 2024",
        "url": "https://www.creativescotland.com/resources/reports",
        "summary": (
            "Scotland's creative industries contribute £5.5 billion GVA annually and employ "
            "over 95,000 people. The sector grew 8.3% year-on-year in 2023–24, outpacing the "
            "UK national average. Edinburgh and Glasgow account for 71% of creative industry "
            "businesses. Key growth sectors: games development (+22%), immersive media (+18%), "
            "and branded content (+14%). Export revenue reached £1.2bn in 2024."
        ),
        "key_stats": {
            "sector_gva": "£5.5bn",
            "employment": "95,000+",
            "yoy_growth": "8.3%",
            "edinburgh_glasgow_share": "71%",
            "export_revenue": "£1.2bn",
        },
    },
    "design_agency_market_scotland": {
        "source": "Design Week Scotland Market Report Q3 2024",
        "url": "https://www.designweek.co.uk/scotland-market-2024",
        "summary": (
            "Scotland has approximately 340 registered design agencies, with 60% based in "
            "Edinburgh/Glasgow. Average project values: branding £8k–£25k, web design £6k–£18k, "
            "full digital campaigns £15k–£50k. Client acquisition predominantly through referrals "
            "(58%) and LinkedIn (27%). Average agency team size: 4–12 people."
        ),
        "key_stats": {
            "agencies_in_scotland": 340,
            "branding_avg_range": "£8k–£25k",
            "web_design_avg_range": "£6k–£18k",
            "digital_campaign_avg_range": "£15k–£50k",
            "referral_acquisition": "58%",
        },
    },
    "music_industry_scotland": {
        "source": "Scottish Music Industry Association (SMIA) 2024 State of the Nation",
        "url": "https://www.smia.org.uk/state-of-the-nation-2024",
        "summary": (
            "Scotland's music industry generates £210m annually. Independent labels represent "
            "34% of all Scottish music releases. Edinburgh and Glasgow dominate with 80% of "
            "music businesses. Streaming revenues up 18% YoY. Key marketing channels: TikTok "
            "(fastest growing, +41%), Instagram (most used, 87% of artists), Spotify editorial "
            "playlisting (highest ROI). Average brand campaign budget for independent labels: £8k–£20k."
        ),
        "key_stats": {
            "industry_value": "£210m",
            "indie_label_share": "34%",
            "streaming_growth": "+18% YoY",
            "tiktok_growth": "+41%",
            "avg_brand_campaign": "£8k–£20k",
        },
    },
    "digital_marketing_benchmarks_uk": {
        "source": "HubSpot UK Marketing Benchmarks 2024",
        "url": "https://www.hubspot.com/marketing-statistics/uk-2024",
        "summary": (
            "UK digital marketing benchmarks 2024: Average email open rate 38.5% (creative sector 42%). "
            "Paid social CPM: Meta £6.20, TikTok £3.80, LinkedIn £28.50. "
            "Average conversion rate landing pages: 3.2%. "
            "Social media ad ROAS benchmarks: e-commerce 3.5x, events/entertainment 3.8x, B2B 2.1x. "
            "Agency retainer average: £2,500–£6,000/month for SMEs."
        ),
        "key_stats": {
            "email_open_rate_creative": "42%",
            "meta_cpm": "£6.20",
            "tiktok_cpm": "£3.80",
            "avg_roas_events": "3.8x",
            "email_roi_multiplier": "36x",
        },
    },
    "competitor_analysis_edinburgh_agencies": {
        "source": "Clutch.co Scotland Agency Directory + LinkedIn Intelligence 2024",
        "url": "https://clutch.co/agencies/scotland",
        "summary": (
            "Top creative/digital agencies in Edinburgh: "
            "(1) Whitespace — 45-person full-service agency, avg project £20k–£80k, strong in NHS/public sector. "
            "(2) Raise the Bar Digital — 12-person performance marketing, avg project £10k–£35k, hospitality/tourism. "
            "(3) Tangent — 8-person branding studio, avg project £8k–£22k, craft beer/food brands. "
            "(4) Found — 20-person SEO/content agency, avg project £6k–£18k/year retainer, tech sector."
        ),
        "competitors": [
            {"name": "Whitespace", "size": "45 staff", "avg_project": "£20k–£80k", "strength": "Public sector, large campaigns"},
            {"name": "Raise the Bar Digital", "size": "12 staff", "avg_project": "£10k–£35k", "strength": "Hospitality, tourism"},
            {"name": "Tangent", "size": "8 staff", "avg_project": "£8k–£22k", "strength": "Food & drink branding"},
            {"name": "Found", "size": "20 staff", "avg_project": "£6k–£18k retainer", "strength": "SEO, tech sector"},
        ],
    },
    "competitor_analysis_glasgow_agencies": {
        "source": "Clutch.co Scotland Agency Directory + LinkedIn Intelligence 2024",
        "url": "https://clutch.co/agencies/scotland/glasgow",
        "summary": (
            "Top creative/digital agencies in Glasgow: "
            "(1) Stripe Communications — 30-person integrated agency, strong PR+digital, avg project £15k–£60k. "
            "(2) Distil — 10-person branding studio, design-led, avg project £10k–£30k, architecture/property. "
            "(3) Kite Factory — 6-person digital studio, specialises in Webflow + Framer, avg project £5k–£15k. "
            "(4) Good Agency — 15-person cause-driven agency, charity/third sector, avg project £8k–£25k."
        ),
        "competitors": [
            {"name": "Stripe Communications", "size": "30 staff", "avg_project": "£15k–£60k", "strength": "PR + digital integration"},
            {"name": "Distil", "size": "10 staff", "avg_project": "£10k–£30k", "strength": "Architecture, property branding"},
            {"name": "Kite Factory", "size": "6 staff", "avg_project": "£5k–£15k", "strength": "Webflow, no-code development"},
            {"name": "Good Agency", "size": "15 staff", "avg_project": "£8k–£25k", "strength": "Charity, social impact"},
        ],
    },
    "arts_festival_marketing_scotland": {
        "source": "EventBrite UK Event Marketing Report 2024 + Edinburgh Festivals Impact Study",
        "url": "https://www.eventbrite.co.uk/l/event-marketing-report-uk-2024",
        "summary": (
            "Edinburgh festivals contribute £280m to the local economy annually. "
            "Arts/culture event marketing benchmarks: average audience acquisition cost £4.20 per ticket. "
            "Email marketing drives 31% of ticket sales for arts events. "
            "TikTok emerging as top channel for under-30 arts audiences (+85% engagement vs Instagram). "
            "Average digital marketing spend for mid-size festivals: £12k–£35k per edition."
        ),
        "key_stats": {
            "festival_economy_contribution": "£280m",
            "digital_acquisition_cost_per_ticket": "£4.20",
            "email_ticket_sales_share": "31%",
            "optimal_campaign_lead_time": "8–12 weeks",
        },
    },
    "web_design_trends_2024": {
        "source": "Awwwards + Webflow State of the Web Design 2024",
        "url": "https://www.awwwards.com/trends-2024",
        "summary": (
            "2024 web design trends: (1) AI-generated imagery as design elements (+340% usage). "
            "(2) Bento grid layouts dominating portfolio/product sites. "
            "(3) Micro-interactions and scroll-driven animations (72% of award-winning sites). "
            "(4) Performance as design principle — Core Web Vitals now threshold for premium positioning. "
            "Webflow dominates no-code space with 47% market share for agency-built sites."
        ),
        "key_stats": {
            "webflow_market_share": "47%",
            "avg_webflow_cost": "£6k–£16k",
            "dark_mode_adoption": "38%",
        },
    },
    "budget_benchmarks_creative_projects": {
        "source": "BIMA (British Interactive Media Association) Pricing Guide 2024",
        "url": "https://www.bima.co.uk/pricing-guide-2024",
        "summary": (
            "UK creative agency day rates 2024: Senior Strategist £650–£900/day, "
            "Creative Director £750–£1,100/day, Senior Designer £450–£650/day, "
            "Copywriter £400–£600/day, Developer (senior) £600–£900/day, "
            "Project Manager £350–£500/day, Account Manager £300–£450/day. "
            "Typical project markups: 15–25% agency management fee."
        ),
        "day_rates": {
            "Senior Strategist": "£650–£900",
            "Creative Director": "£750–£1,100",
            "Senior Designer": "£450–£650",
            "Copywriter": "£400–£600",
            "Developer (Senior)": "£600–£900",
            "Project Manager": "£350–£500",
            "Account Manager": "£300–£450",
        },
    },
}
# fmt: on


def _mock_search(query: str) -> dict[str, Any]:
    """Fallback mock search using keyword matching against hardcoded data."""
    query_lower = query.lower()

    # Try exact topic match first
    for key, data in _MOCK_SEARCH_DATA.items():
        if any(word in query_lower for word in key.split("_") if len(word) > 3):
            return {
                "query":   query,
                "answer":  data.get("summary", ""),
                "sources": [{"title": data.get("source", ""), "url": data.get("url", ""), "snippet": data.get("summary", "")[:400]}],
                "mode":    "mock",
                "_raw":    data,
            }

    # Generic fallback
    return {
        "query":   query,
        "answer":  "General Scottish creative industry context applies. See market overview for details.",
        "sources": [],
        "mode":    "mock_fallback",
    }


def _format_mock_result(result: dict) -> str:
    """Format mock result into readable text for the LLM."""
    lines = [f"## Search Results [MOCK]: {result['query']}\n"]
    if result.get("answer"):
        lines.append(f"**Summary:** {result['answer']}\n")

    raw = result.get("_raw", {})
    for key in ("key_stats", "day_rates", "competitors"):
        if raw.get(key):
            lines.append(f"**{key.replace('_', ' ').title()}:**")
            val = raw[key]
            if isinstance(val, dict):
                for k, v in val.items():
                    lines.append(f"  - {k}: {v}")
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        lines.append(f"  - {item.get('name', '')}: {item.get('strength', '')} ({item.get('avg_project', '')})")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def handle_tool_call(tool_name: str, tool_args: str | dict) -> str:
    """
    Dispatch a tool call from the OpenAI API.
    Tries real Tavily search first; falls back to mock data.
    Returns JSON string result.
    """
    if isinstance(tool_args, str):
        args = json.loads(tool_args)
    else:
        args = tool_args

    if tool_name != "web_search":
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    query = args.get("query", "")

    # ── Try real search ──────────────────────────────────────────────────────
    real = _real_search(query)
    if real and "error" not in real:
        formatted = _format_real_result(real)
        return json.dumps({"query": query, "mode": "live", "formatted": formatted}, ensure_ascii=False)

    # ── Fall back to mock ────────────────────────────────────────────────────
    mock = _mock_search(query)
    formatted = _format_mock_result(mock)
    return json.dumps({"query": query, "mode": mock["mode"], "formatted": formatted}, ensure_ascii=False)
