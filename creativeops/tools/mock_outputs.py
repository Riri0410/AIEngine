"""
Mock Output Generators — CreativeOps AI Part 2.

Produces convincing fake structured data for:
  - Project folder structure
  - Calendar milestone blocks
  - Client email preview

All functions are pure (no I/O) and return JSON-serialisable dicts/lists.
"""

import os
import re
from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert a project name to a filesystem-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "_", slug)
    return slug.strip("_")


def _parse_date(date_str: str) -> date:
    """Parse ISO date string or return today on failure."""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return date.today()


def _next_weekday(d: date) -> date:
    """Advance d past weekends so milestones always land on Mon–Fri."""
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d += timedelta(days=1)
    return d


# ---------------------------------------------------------------------------
# 1. Folder structure
# ---------------------------------------------------------------------------

def mock_folder_structure(project_name: str) -> dict:
    """
    Return a fake project directory tree.

    Args:
        project_name: Human-readable project name (e.g. "Tartan Audio Rebrand")

    Returns:
        {
            "root": "projects/<slug>/",
            "folders": [...],
            "files": { "folder_name": [...], ... }
        }
    """
    slug = _slugify(project_name)

    return {
        "root": f"projects/{slug}/",
        "folders": [
            "01_brief",
            "02_research",
            "03_creative",
            "04_production",
            "05_delivery",
            "06_admin",
        ],
        "files": {
            "01_brief": [
                "client_brief.pdf",
                "kick_off_notes.md",
                "stakeholder_contacts.md",
            ],
            "02_research": [
                "competitor_analysis.md",
                "market_research_report.pdf",
                "audience_personas.md",
                "brand_audit.pdf",
            ],
            "03_creative": [
                "moodboard_v1.pdf",
                "concepts_presentation_v1.pptx",
                "concepts_presentation_v2.pptx",
                "brand_assets/",
                "copy_drafts_v1.docx",
            ],
            "04_production": [
                "design_files/",
                "approved_assets/",
                "revision_notes.md",
                "qa_checklist.md",
            ],
            "05_delivery": [
                "final_assets.zip",
                "handover_guide.pdf",
                "usage_guidelines.pdf",
            ],
            "06_admin": [
                "contract_draft.docx",
                "invoice_template.xlsx",
                "proposal_v1.pdf",
                "project_timeline.xlsx",
                "change_log.md",
            ],
        },
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "project_slug": slug,
    }


# ---------------------------------------------------------------------------
# 2. Calendar milestone blocks
# ---------------------------------------------------------------------------

# Milestone templates: (label, event_type, offset_fraction, duration_minutes)
# offset_fraction: 0.0 = project start, 1.0 = project end
_MILESTONE_TEMPLATES = [
    ("Kickoff Call",                    "call",         0.00,  60),
    ("Discovery Workshop",              "workshop",     0.06,  120),
    ("Brief & Strategy Sign-off",       "approval",     0.12,  30),
    ("Research Delivery (Internal)",    "internal",     0.20,  60),
    ("Initial Creative Concepts",       "presentation", 0.35,  90),
    ("Client Review — Creative Direction", "approval",  0.45,  60),
    ("Revised Concepts Delivery",       "delivery",     0.55,  60),
    ("Final Creative Sign-off",         "approval",     0.65,  30),
    ("Production Assets Complete",      "internal",     0.75,  60),
    ("Final Client Presentation",       "presentation", 0.85,  90),
    ("Final Delivery & Handover",       "delivery",     1.00,  60),
]

_EVENT_TYPE_ICONS = {
    "call":         "📞",
    "workshop":     "🛠️",
    "approval":     "✅",
    "internal":     "🔒",
    "presentation": "📊",
    "delivery":     "📦",
}

_WORKING_HOUR_BY_TYPE = {
    "call":         9,
    "workshop":     10,
    "approval":     14,
    "internal":     9,
    "presentation": 11,
    "delivery":     10,
}


def mock_calendar_blocks(start_date: str, weeks: int) -> list[dict]:
    """
    Generate realistic project milestone calendar events.

    Args:
        start_date: ISO date string for project start (e.g. "2025-04-07")
        weeks: Total project duration in weeks (typically 4–12)

    Returns:
        List of calendar event dicts sorted by date, each with:
          { date, time, title, type, icon, duration_minutes, week_number, description }
    """
    if weeks < 1:
        weeks = 4

    start = _parse_date(start_date)
    total_days = weeks * 7
    events = []

    for label, event_type, fraction, duration in _MILESTONE_TEMPLATES:
        offset_days = int(round(total_days * fraction))
        raw_date = start + timedelta(days=offset_days)
        event_date = _next_weekday(raw_date)

        hour = _WORKING_HOUR_BY_TYPE.get(event_type, 10)
        icon = _EVENT_TYPE_ICONS.get(event_type, "📅")

        # Which week of the project this falls in
        delta = (event_date - start).days
        week_number = max(1, (delta // 7) + 1)

        events.append({
            "date": event_date.isoformat(),
            "time": f"{hour:02d}:00",
            "title": label,
            "type": event_type,
            "icon": icon,
            "duration_minutes": duration,
            "week_number": week_number,
            "description": _milestone_description(label, event_type),
            "attendees": _milestone_attendees(event_type),
            "location": "Google Meet" if event_type in ("call", "presentation", "approval") else "Internal",
        })

    # Sort by date then time
    events.sort(key=lambda e: (e["date"], e["time"]))
    return events


def _milestone_description(label: str, event_type: str) -> str:
    descriptions = {
        "Kickoff Call": "Introductory call to align on project goals, timeline, and key contacts. Client + agency leads attend.",
        "Discovery Workshop": "Deep-dive session to understand brand, audience, and project constraints. Outputs: brief confirmation + creative direction brief.",
        "Brief & Strategy Sign-off": "Client approves the confirmed brief and strategic direction before creative work begins.",
        "Research Delivery (Internal)": "Internal handover of market research, competitor analysis, and audience personas to the creative team.",
        "Initial Creative Concepts": "Presentation of 2–3 initial creative directions for client feedback. No final decisions at this stage.",
        "Client Review — Creative Direction": "Client selects preferred creative direction and provides consolidated feedback.",
        "Revised Concepts Delivery": "Delivery of refined concepts incorporating client feedback from the direction review.",
        "Final Creative Sign-off": "Client provides written approval of final creative direction before production begins.",
        "Production Assets Complete": "All production-ready files prepared internally and queued for final review.",
        "Final Client Presentation": "Presentation of all completed deliverables. Final amends raised here.",
        "Final Delivery & Handover": "All final files delivered via agreed channel. Handover guide and asset documentation included.",
    }
    return descriptions.get(label, f"{event_type.capitalize()} milestone for this project phase.")


def _milestone_attendees(event_type: str) -> list[str]:
    mapping = {
        "call":         ["Account Manager", "Client Lead"],
        "workshop":     ["Creative Director", "Strategist", "Client Lead", "Client Team"],
        "approval":     ["Account Manager", "Client Lead"],
        "internal":     ["Creative Director", "Designer", "Strategist"],
        "presentation": ["Account Manager", "Creative Director", "Client Lead", "Client Team"],
        "delivery":     ["Account Manager", "Client Lead"],
    }
    return mapping.get(event_type, ["Account Manager", "Client Lead"])


# ---------------------------------------------------------------------------
# 3. Email preview
# ---------------------------------------------------------------------------

def mock_email_preview(client_name: str, proposal_summary: str) -> dict:
    """
    Generate a professional client-ready email preview containing the proposal.

    Args:
        client_name: Client organisation name (e.g. "Tartan Audio")
        proposal_summary: First ~800 chars of the proposal text (used as context)

    Returns:
        {
            "to": "...", "subject": "...", "body": "...",
            "status": "PREVIEW — not sent"
        }
    """
    # DEMO_CLIENT_EMAIL lets you override the recipient to YOUR own address so
    # judges watch a real email land on your phone during the demo.
    demo_override = os.environ.get("DEMO_CLIENT_EMAIL", "").strip()
    if demo_override and "@" in demo_override:
        to_address = demo_override
    else:
        email_slug = _slugify(client_name).replace("_", "")
        to_address = f"hello@{email_slug}.com"

    # Extract project name from summary (first line after # or first sentence)
    project_name = _extract_project_name_from_summary(proposal_summary, client_name)

    subject = f"Your CreativeOps Proposal — {project_name}"

    # Build the email body.
    # Use a platform-safe day format (Windows does not support %-d in strftime).
    today = date.today()
    today_str = f"{today.day} {today.strftime('%B %Y')}"

    body = f"""Hi there,

Thank you for taking the time to speak with us about your upcoming project — it was great to learn more about {client_name} and what you're looking to achieve.

Please find attached our proposal for **{project_name}**. We've put together a detailed scope of work, timeline, and investment breakdown tailored specifically to your brief and objectives.

**A few highlights from the proposal:**

{_extract_highlights(proposal_summary)}

We're genuinely excited about this project and believe we're well-placed to deliver results that make a real difference for {client_name}. Our team has deep experience in the Scottish creative market and a track record of delivering on time and on budget.

**Next steps:**

1. Review the attached proposal at your convenience
2. Let us know if you have any questions or would like to talk anything through
3. If you're happy to proceed, we'll send over a formal contract and schedule a kickoff call

We'd love to get started. If you're ready to move forward, simply reply to this email or book a 30-minute call using the link below.

Looking forward to hearing from you.

Warm regards,

**CreativeOps Studio**
hello@creativeops.studio | +44 131 000 0000
Edinburgh | Glasgow

---
*This proposal is valid for 30 days from the date of issue ({today_str}).*
*All prices quoted exclude VAT unless stated otherwise.*"""

    return {
        "to": to_address,
        "cc": "",
        "subject": subject,
        "body": body,
        "attachments": ["proposal_v1.pdf", "contract_draft.docx"],
        "status": "PREVIEW — not sent",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# 4. Contract / SOW document generator
# ---------------------------------------------------------------------------

def mock_contract_document(
    project_name: str,
    client_name: str,
    total_budget: int,
    weeks: int,
    risk_output: dict | None = None,
    kai_output: dict | None = None,
) -> dict:
    """
    Generate a professional Statement of Work / contract document.

    Uses Riley's risk register and Kai's commercial terms to build
    a tailored contract with appropriate protections.
    """
    today = date.today()
    today_str = f"{today.day} {today.strftime('%B %Y')}"
    start_date = _next_weekday(today + timedelta(days=7))
    end_date = _next_weekday(start_date + timedelta(weeks=weeks))

    # Pull contract terms from agents (with sensible defaults)
    kai = kai_output or {}
    riley = risk_output or {}
    walk_away = kai.get("walk_away_point", f"£{int(total_budget * 0.8):,}")
    concessions = kai.get("concession_ladder", [])
    risks = riley.get("risk_register", [])
    missing = riley.get("missing_from_brief", [])

    # Build scope protection clauses from Riley's risks
    scope_clauses = []
    for r in risks[:3]:
        addition = r.get("proposal_addition", "")
        if addition:
            scope_clauses.append(f"- {addition}")
    if not scope_clauses:
        scope_clauses = [
            "- Deliverables are as listed in the attached proposal only",
            "- Any additional work outside this scope will be quoted separately",
        ]

    # Questions to ask before signing
    questions = riley.get("questions_to_ask", [
        "Who is the single point of approval for all creative sign-offs?",
        "When will existing brand assets and content be provided to the team?",
    ])

    sow_text = f"""# STATEMENT OF WORK
## {project_name}

**Client:** {client_name}
**Agency:** CreativeOps Studio
**Date:** {today_str}
**Project Start:** {start_date.strftime('%d %B %Y')}
**Project End:** {end_date.strftime('%d %B %Y')}
**Total Investment:** £{total_budget:,} + VAT

---

## 1. SCOPE OF WORK

The deliverables for this engagement are defined in the attached proposal document.

**Scope protections:**
{chr(10).join(scope_clauses)}

---

## 2. PAYMENT TERMS

| Milestone | Amount | Due |
|-----------|--------|-----|
| Project kickoff (deposit) | £{int(total_budget * 0.5):,} | Upon contract signature |
| Mid-project delivery | £{int(total_budget * 0.25):,} | Week {max(1, weeks // 2)} |
| Final delivery & sign-off | £{int(total_budget * 0.25):,} | Week {weeks} |

**Payment due within 14 days of invoice. Late payment: 2% per month.**

---

## 3. REVISION ROUNDS

This project includes **2 rounds of consolidated revisions** per deliverable phase.
Additional revision rounds are chargeable at day rates as per our rate card.

*All feedback to be provided in a single, consolidated document per revision round.*

---

## 4. KILL FEE

In the event the client cancels this project after kickoff:
- Before Week {max(1, weeks // 4)}: 25% of total project value
- After Week {max(1, weeks // 4)}: 50% of total project value
- After 75% completion: 100% of total project value

---

## 5. INTELLECTUAL PROPERTY

All intellectual property created during this engagement transfers to {client_name} upon receipt of **final payment in full**.
CreativeOps Studio retains the right to display this work in our portfolio unless agreed otherwise in writing.

---

## 6. CLIENT RESPONSIBILITIES

To avoid project delays, {client_name} agrees to:
- Provide all existing brand assets and content within **3 business days** of kickoff
- Assign a single named decision-maker for all creative approvals
- Respond to review requests within **3 business days**
- Provide consolidated feedback (not multiple conflicting sets)

*Delays caused by late client feedback may result in timeline extensions and/or additional charges.*

---

## 7. OPEN QUESTIONS (pre-contract)

Before signing, please confirm the following:
{chr(10).join(f"{i+1}. {q}" for i, q in enumerate(questions[:4]))}

---

## 8. SIGNATURES

| | CreativeOps Studio | {client_name} |
|-|-------------------|{'-' * len(client_name)}|
| **Signed** | __________________ | __________________ |
| **Name** | __________________ | __________________ |
| **Date** | __________________ | __________________ |

---

*This Statement of Work is governed by Scottish law and subject to CreativeOps Studio's Standard Terms of Business.*
*This document is valid for 30 days from {today_str}.*"""

    return {
        "document_title": f"SOW — {project_name}",
        "client_name": client_name,
        "total_budget": total_budget,
        "weeks": weeks,
        "risk_level": riley.get("overall_risk_level", "medium"),
        "go_no_go": riley.get("go_no_go", "go"),
        "sow_text": sow_text,
        "open_questions": questions,
        "concession_ladder": concessions,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def _extract_project_name_from_summary(summary: str, client_name: str) -> str:
    """
    Try to pull the project/proposal title from the first heading in the summary.
    Falls back to a generic name.
    """
    # Match markdown h1: # Title
    match = re.search(r"^#\s+(.+)$", summary, re.MULTILINE)
    if match:
        title = match.group(1).strip()
        # Strip common boilerplate
        title = re.sub(r"—\s*project proposal.*", "", title, flags=re.IGNORECASE).strip()
        if title:
            return title

    # Fall back: use client name + "Project Proposal"
    return f"{client_name} — Project Proposal"


def _extract_highlights(summary: str) -> str:
    """
    Pull 2–3 bullet-point highlights from the proposal text.
    Looks for existing bullet lists, or constructs generic highlights.
    """
    # Try to find existing bullet lines
    bullets = re.findall(r"^\s*[-*•]\s+(.+)$", summary, re.MULTILINE)

    if len(bullets) >= 2:
        chosen = bullets[:3]
        return "\n".join(f"- {b.strip()}" for b in chosen)

    # Fallback: generic but professional highlights
    return (
        "- A clearly scoped deliverables list with no hidden extras\n"
        "- A realistic, week-by-week project timeline\n"
        "- A fully itemised budget breakdown with transparent day rates"
    )
