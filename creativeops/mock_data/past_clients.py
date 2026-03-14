"""
Mock historical client data simulating a RAG/memory store.
Used to ground proposals with realistic Scottish creative industry context.
"""

PAST_CLIENTS = [
    {
        "id": "wavefront-records-2023",
        "client_name": "Wavefront Records",
        "industry": "Music / Entertainment",
        "location": "Edinburgh, Scotland",
        "project_type": "Brand Campaign",
        "budget": 12000,
        "currency": "GBP",
        "duration_weeks": 8,
        "year": 2023,
        "brief_summary": (
            "Rebrand and launch campaign for an independent Edinburgh music label "
            "focused on electronic and ambient artists. Needed visual identity refresh, "
            "social media assets, and a 6-week digital launch campaign targeting "
            "18–35 music enthusiasts across Scotland and the UK."
        ),
        "deliverables": [
            "Logo redesign + brand guidelines (30 pages)",
            "Social media template pack (Instagram, TikTok, X)",
            "3× artist spotlight short-form videos (60s each)",
            "Email newsletter design + 4-issue campaign",
            "Spotify Canvas animations for 5 tracks",
            "Press kit PDF",
        ],
        "outcome": (
            "Campaign achieved 42k organic impressions in week 1. Label signed "
            "2 new artists within 3 months. Client rated delivery 9/10."
        ),
        "lessons_learned": (
            "Spotify Canvas deliverables took 40% longer than estimated. "
            "Buffer animation revisions into timeline. Client comms via Slack "
            "worked better than email for this sector."
        ),
        "budget_breakdown": {
            "Strategy & Discovery": 1500,
            "Brand Identity Design": 3200,
            "Video Production": 2800,
            "Social Media Assets": 1800,
            "Email Campaign": 1200,
            "Project Management": 800,
            "Contingency (8%)": 700,
        },
        "tags": ["music", "branding", "edinburgh", "digital", "social media"],
    },
    {
        "id": "glasswork-studio-2023",
        "client_name": "Glasswork Studio",
        "industry": "Architecture / Interior Design",
        "location": "Glasgow, Scotland",
        "project_type": "Website Redesign",
        "budget": 8000,
        "currency": "GBP",
        "duration_weeks": 6,
        "year": 2023,
        "brief_summary": (
            "Full redesign of portfolio website for a boutique Glasgow architecture "
            "and interior design studio. Required a premium, minimal aesthetic to "
            "showcase residential and commercial projects. SEO uplift and mobile "
            "performance were key success metrics."
        ),
        "deliverables": [
            "UX/UI design (wireframes + high-fidelity mockups)",
            "Webflow development (15 pages)",
            "Project portfolio CMS setup (25 case studies migrated)",
            "SEO audit + on-page optimisation",
            "Photography art direction brief for 2 shoot days",
            "Analytics dashboard (GA4 + Hotjar)",
            "Handover documentation + 1-hour training session",
        ],
        "outcome": (
            "Page load time reduced from 6.2s to 1.4s. Organic search traffic "
            "up 68% in 3 months post-launch. Client secured 3 new commissions "
            "directly attributed to the site redesign."
        ),
        "lessons_learned": (
            "Photography dependency caused a 10-day delay — always schedule "
            "client-owned assets (photos, copy) as critical path items. "
            "Webflow CMS training needed more time than allocated."
        ),
        "budget_breakdown": {
            "Discovery & UX Research": 1000,
            "UI Design": 2200,
            "Webflow Development": 2800,
            "SEO & Analytics": 800,
            "Content Migration": 600,
            "Training & Handover": 400,
            "Contingency (5%)": 200,
        },
        "tags": ["architecture", "web design", "glasgow", "webflow", "seo", "portfolio"],
    },
    {
        "id": "fringe-forward-2024",
        "client_name": "Fringe Forward",
        "industry": "Arts & Culture / Events",
        "location": "Edinburgh, Scotland",
        "project_type": "Digital Marketing Campaign",
        "budget": 20000,
        "currency": "GBP",
        "duration_weeks": 12,
        "year": 2024,
        "brief_summary": (
            "End-to-end digital marketing campaign for an Edinburgh arts festival "
            "running across 3 weeks in August. Objectives: sell 85% of ticket "
            "inventory pre-festival, grow social following by 5k, and build an "
            "email list of 10k subscribers for future editions."
        ),
        "deliverables": [
            "Campaign strategy document + audience personas",
            "Paid social ads (Meta + TikTok): 24 ad creatives",
            "Google Ads campaign (Search + Display)",
            "Weekly organic social content (3× platforms, 12 weeks)",
            "Email marketing automation (welcome sequence + 8 broadcast emails)",
            "Influencer outreach + coordination (6 local arts influencers)",
            "Weekly performance reports + mid-campaign optimisation",
            "Post-campaign analytics report",
        ],
        "outcome": (
            "91% ticket sell-through rate (exceeded target). Social following grew "
            "by 7.2k. Email list reached 11.4k subscribers. ROAS on paid social: 4.1x."
        ),
        "lessons_learned": (
            "TikTok ads outperformed Meta by 2.3x on cost-per-click for 18–28 age bracket. "
            "Influencer contracts need clearer IP clauses for repurposing content. "
            "Weekly client check-ins (30 min) were essential for a fast-moving campaign."
        ),
        "budget_breakdown": {
            "Strategy & Planning": 2500,
            "Creative Production (ads + social)": 4500,
            "Paid Media Management": 2000,
            "Paid Media Ad Spend (passed through)": 5000,
            "Email Marketing": 1800,
            "Influencer Management": 2000,
            "Analytics & Reporting": 1200,
            "Account Management": 1000,
        },
        "tags": [
            "arts", "events", "festival", "edinburgh", "paid social",
            "email marketing", "influencer", "ticketing",
        ],
    },
]


def get_relevant_clients(brief: str, max_results: int = 2) -> list[dict]:
    """
    Simple keyword-based retrieval to simulate RAG.
    Returns past clients whose tags or industry overlap with the brief.
    """
    brief_lower = brief.lower()
    scored = []
    for client in PAST_CLIENTS:
        score = 0
        for tag in client["tags"]:
            if tag in brief_lower:
                score += 2
        for keyword in [client["industry"].lower(), client["location"].lower(),
                        client["project_type"].lower()]:
            if any(word in brief_lower for word in keyword.split()):
                score += 1
        scored.append((score, client))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:max_results]]


def format_client_context(clients: list[dict]) -> str:
    """Format past client records into a readable context string for prompts."""
    if not clients:
        return "No closely matching past projects found."

    lines = ["## Relevant Past Projects (Internal Memory)\n"]
    for c in clients:
        lines.append(f"### {c['client_name']} — {c['project_type']} (£{c['budget']:,})")
        lines.append(f"- **Industry:** {c['industry']} | **Location:** {c['location']}")
        lines.append(f"- **Duration:** {c['duration_weeks']} weeks | **Year:** {c['year']}")
        lines.append(f"- **Brief:** {c['brief_summary']}")
        lines.append(f"- **Outcome:** {c['outcome']}")
        lines.append(f"- **Lessons:** {c['lessons_learned']}")
        lines.append("- **Budget Breakdown:**")
        for item, cost in c["budget_breakdown"].items():
            lines.append(f"  - {item}: £{cost:,}")
        lines.append("")
    return "\n".join(lines)
