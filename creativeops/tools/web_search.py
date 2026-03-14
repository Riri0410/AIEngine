"""
Mock web search tool for the Research Agent.
Returns hardcoded, realistic data about the Scottish creative industry,
competitors, and market benchmarks. Simulates real search results.
"""

import json
import re
from typing import Any

# ---------------------------------------------------------------------------
# Mock search result database keyed by topic/query patterns
# ---------------------------------------------------------------------------

MOCK_SEARCH_DATA: dict[str, dict[str, Any]] = {
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
            "(58%) and LinkedIn (27%). Average agency team size: 4–12 people. "
            "Top challenges: talent retention (67%), client budget pressure (54%), AI integration (49%)."
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
            "music businesses. Streaming revenues up 18% YoY. Live events recovered to 94% of "
            "pre-pandemic levels. Key marketing channels: TikTok (fastest growing, +41%), "
            "Instagram (most used, 87% of artists), Spotify editorial playlisting (highest ROI). "
            "Average brand campaign budget for independent labels: £8k–£20k."
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
            "Content marketing ROI: blog +4.5x, video +6.2x, email +36x. "
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
            "(1) Whitespace — 45-person full-service agency, Trustpilot 4.8, avg project £20k–£80k, strong in NHS/public sector. "
            "(2) Raise the Bar Digital — 12-person performance marketing, avg project £10k–£35k, specialises in hospitality/tourism. "
            "(3) Tangent — 8-person branding studio, avg project £8k–£22k, known for craft beer/food brands. "
            "(4) Found — 20-person SEO/content agency, avg project £6k–£18k/year retainer, tech sector focus. "
            "Differentiators that win work: local market knowledge, transparent pricing, specialist sector expertise."
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
            "(2) Distil — 10-person branding studio, design-led, avg project £10k–£30k, architecture/property clients. "
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
            "Arts/culture event marketing benchmarks: average audience acquisition cost £4.20 per ticket (digital channels). "
            "Email marketing drives 31% of ticket sales for arts events. "
            "Social proof (reviews + press coverage) influences 67% of purchase decisions. "
            "Lead time: campaigns should launch 8–12 weeks before events for optimal sell-through. "
            "TikTok emerging as top channel for under-30 arts audiences (+85% engagement vs Instagram). "
            "Average digital marketing spend for mid-size festivals: £12k–£35k per edition."
        ),
        "key_stats": {
            "festival_economy_contribution": "£280m",
            "digital_acquisition_cost_per_ticket": "£4.20",
            "email_ticket_sales_share": "31%",
            "social_proof_influence": "67%",
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
            "(4) Dark mode as default (38% of new launches). "
            "(5) Performance as design principle — Core Web Vitals now threshold for premium positioning. "
            "Webflow dominates no-code space with 47% market share for agency-built sites. "
            "Average Webflow site: 15–25 pages, £6k–£16k delivery cost for agencies."
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
            "Typical project markups: 15–25% agency management fee. "
            "Rush fee (under 2-week delivery): +30–50% uplift. "
            "IP/usage rights fees: +10–20% of production cost for perpetual licensing."
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

# ---------------------------------------------------------------------------
# Tool definition (OpenAI function calling schema)
# ---------------------------------------------------------------------------

WEB_SEARCH_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the web for information about a client, their industry, competitors, "
            "and market benchmarks relevant to the Scottish creative industry. "
            "Returns structured research data."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The search query. Examples: 'Scottish music industry market size', "
                        "'Edinburgh design agency competitors', 'UK digital marketing benchmarks 2024'"
                    ),
                },
                "topic": {
                    "type": "string",
                    "enum": [
                        "scottish_creative_industry_overview",
                        "design_agency_market_scotland",
                        "music_industry_scotland",
                        "digital_marketing_benchmarks_uk",
                        "competitor_analysis_edinburgh_agencies",
                        "competitor_analysis_glasgow_agencies",
                        "arts_festival_marketing_scotland",
                        "web_design_trends_2024",
                        "budget_benchmarks_creative_projects",
                    ],
                    "description": "The topic category for the search to get most relevant results.",
                },
            },
            "required": ["query", "topic"],
        },
    },
}


# ---------------------------------------------------------------------------
# Mock executor
# ---------------------------------------------------------------------------

def execute_web_search(query: str, topic: str) -> dict[str, Any]:
    """
    Execute a mock web search. Returns hardcoded realistic data.
    In production this would call a real search API (e.g. Brave, Serper, Tavily).
    """
    result = MOCK_SEARCH_DATA.get(topic)
    if result:
        return {
            "query": query,
            "topic": topic,
            "status": "success",
            "result": result,
        }

    # Fallback: fuzzy match on any topic containing key words
    query_lower = query.lower()
    for key, data in MOCK_SEARCH_DATA.items():
        if any(word in query_lower for word in key.split("_")):
            return {
                "query": query,
                "topic": key,
                "status": "partial_match",
                "result": data,
            }

    return {
        "query": query,
        "topic": topic,
        "status": "no_results",
        "result": {
            "summary": (
                "No specific data found for this query. "
                "General Scottish creative industry context applies."
            )
        },
    }


def handle_tool_call(tool_name: str, tool_args: str | dict) -> str:
    """
    Handle a tool call from the OpenAI API.
    Parses args and returns JSON string result.
    """
    if isinstance(tool_args, str):
        args = json.loads(tool_args)
    else:
        args = tool_args

    if tool_name == "web_search":
        result = execute_web_search(
            query=args.get("query", ""),
            topic=args.get("topic", "scottish_creative_industry_overview"),
        )
        return json.dumps(result, indent=2)

    return json.dumps({"error": f"Unknown tool: {tool_name}"})
