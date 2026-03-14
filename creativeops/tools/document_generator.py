"""
Document Generator — CreativeOps AI

Generates real, downloadable PDF documents from the pipeline outputs.
Uses fpdf2 (pure Python — no system dependencies required).

Documents are written to a session temp directory and served by the
/download/{filename} FastAPI endpoint.

Concurrent generation is handled by the caller via asyncio + run_in_executor
so each PDF is built in a thread pool without blocking the event loop.
"""

import asyncio
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── fpdf2 (optional dependency) ─────────────────────────────────────────────
try:
    from fpdf import FPDF
    _FPDF_AVAILABLE = True
except ImportError:
    FPDF = object
    _FPDF_AVAILABLE = False
    FPDF = object  # dummy base so the class definition below doesn't NameError

# ---------------------------------------------------------------------------
# File storage
# ---------------------------------------------------------------------------

_OUTPUT_DIR = Path(tempfile.gettempdir()) / "creativeops_docs"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_output_dir() -> Path:
    return _OUTPUT_DIR


def get_download_path(filename: str) -> Optional[Path]:
    """Return the full path for a generated file, or None if it doesn't exist."""
    p = _OUTPUT_DIR / filename
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "_", slug)
    return slug.strip("_")[:40]


def _strip_md(text: str) -> str:
    """Strip the most common markdown syntax for plain-text PDF rendering."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"\*(.+?)\*",     r"\1", text)
    text = re.sub(r"__(.+?)__",     r"\1", text)
    text = re.sub(r"_(.+?)_",       r"\1", text)
    text = re.sub(r"```.*?```",      "",   text, flags=re.DOTALL)
    text = re.sub(r"`(.+?)`",        r"\1", text)
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    text = re.sub(r"<!--.*?-->",     "",   text, flags=re.DOTALL)
    return text.strip()


# ---------------------------------------------------------------------------
# PDF class
# ---------------------------------------------------------------------------

class _ProposalPDF(FPDF):
    """
    A styled FPDF subclass that renders a markdown-ish proposal document.

    Design: clean white background, amber accent headings, professional
    layout — suitable for sending directly to clients.
    """

    AMBER   = (180, 120, 10)
    DARK    = (30, 30, 35)
    BODY    = (60, 60, 68)
    SUBTLE  = (140, 140, 150)
    DIVIDER = (220, 220, 225)
    WHITE   = (255, 255, 255)

    def __init__(self, doc_title: str, client_name: str = ""):
        super().__init__()
        self.doc_title   = doc_title
        self.client_name = client_name
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(18, 18, 18)

    # ── Page chrome ─────────────────────────────────────────────────────────

    def header(self):
        # Amber top bar
        self.set_fill_color(180, 120, 10)
        self.rect(0, 0, 210, 4, "F")
        # White space
        self.set_fill_color(*self.WHITE)
        self.rect(0, 4, 210, 16, "F")

        if self.page_no() == 1:
            # Big title on page 1
            self.set_xy(18, 6)
            self.set_font("Helvetica", "B", 13)
            self.set_text_color(*self.DARK)
            self.cell(120, 8, "CreativeOps Studio", ln=False)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*self.SUBTLE)
            self.set_xy(18, 13)
            self.cell(0, 5, f"Proposal — {datetime.now().strftime('%d %B %Y')}")
        else:
            self.set_xy(18, 8)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(*self.SUBTLE)
            self.cell(0, 5, f"CreativeOps Studio  ·  {self.doc_title[:70]}")

        self.ln(10)

    def footer(self):
        self.set_y(-14)
        # Thin amber rule
        self.set_draw_color(180, 120, 10)
        self.set_line_width(0.3)
        self.line(18, self.get_y(), 192, self.get_y())
        self.ln(2)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(*self.SUBTLE)
        self.cell(0, 5,
            f"Page {self.page_no()}  ·  Confidential  ·  Valid 30 days from date of issue",
            align="C")

    # ── Section renderers ────────────────────────────────────────────────────

    def h1(self, text: str):
        self.ln(5)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*self.DARK)
        self.multi_cell(0, 8, _strip_md(text))
        # Amber underline
        y = self.get_y()
        self.set_draw_color(*self.AMBER)
        self.set_line_width(0.8)
        self.line(18, y, 192, y)
        self.ln(4)

    def h2(self, text: str):
        self.ln(6)
        self.set_fill_color(252, 245, 220)       # very light amber tint
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*self.AMBER)
        self.multi_cell(0, 6, _strip_md(text), fill=False)
        self.ln(1)

    def h3(self, text: str):
        self.ln(3)
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(*self.DARK)
        self.multi_cell(0, 5, _strip_md(text))
        self.ln(0.5)

    def paragraph(self, text: str):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*self.BODY)
        self.multi_cell(0, 5, _strip_md(text))
        self.ln(1.5)

    def bullet(self, text: str):
        self.set_font("Helvetica", "", 9)
        self.set_text_color(*self.BODY)
        x = self.get_x()
        self.set_x(22)
        self.cell(5, 5, "\u2022", ln=False)        # bullet char
        self.set_x(27)
        text_clean = _strip_md(re.sub(r"^[-*\u2022]\s*", "", text).strip())
        self.multi_cell(0, 5, text_clean)

    def hr(self):
        self.ln(2)
        self.set_draw_color(*self.DIVIDER)
        self.set_line_width(0.2)
        self.line(18, self.get_y(), 192, self.get_y())
        self.ln(3)

    def table_row(self, cells: list[str], is_header: bool = False):
        col_widths = [70, 30, 30, 44]
        if is_header:
            self.set_fill_color(240, 230, 200)
            self.set_font("Helvetica", "B", 8)
            self.set_text_color(*self.DARK)
        else:
            self.set_fill_color(252, 252, 252)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(*self.BODY)

        for i, (cell, w) in enumerate(zip(cells, col_widths)):
            self.cell(w, 6, _strip_md(str(cell))[:35], border="B", fill=is_header, align="L")
        self.ln()


# ---------------------------------------------------------------------------
# Markdown → PDF renderer
# ---------------------------------------------------------------------------

def _render_markdown(pdf: "_ProposalPDF", md_text: str):
    """Walk the markdown line-by-line and call the appropriate PDF renderer."""
    table_rows: list[str] = []
    in_table = False

    def _flush_table():
        nonlocal in_table, table_rows
        for idx, row in enumerate(table_rows):
            cells = [c.strip() for c in row.strip("|").split("|")]
            pdf.table_row(cells, is_header=(idx == 0))
        table_rows = []
        in_table = False
        pdf.ln(2)

    for raw_line in md_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        # Flush table if we hit a non-table line
        if in_table and not stripped.startswith("|"):
            _flush_table()

        if not stripped:
            if in_table:
                pass
            else:
                pdf.ln(2)
        elif stripped.startswith("# "):
            pdf.h1(stripped[2:])
        elif stripped.startswith("## "):
            pdf.h2(stripped[3:])
        elif stripped.startswith("### "):
            pdf.h3(stripped[4:])
        elif stripped.startswith("|"):
            # Skip markdown separator rows like |---|---|
            if re.fullmatch(r"[|\s:\-]+", stripped):
                continue
            in_table = True
            table_rows.append(stripped)
        elif re.match(r"^\s*[-*\u2022]\s+", line):
            pdf.bullet(stripped)
        elif stripped in ("---", "***", "___"):
            pdf.hr()
        else:
            pdf.paragraph(stripped)

    if in_table:
        _flush_table()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_proposal_pdf(
    proposal_text: str,
    project_name: str = "Project Proposal",
    client_name: str  = "Client",
) -> str | None:
    """
    Generate a PDF from the proposal markdown text synchronously.

    Returns:
        The absolute file path of the generated PDF, or None if fpdf2 is
        not installed.
    """
    if not _FPDF_AVAILABLE:
        return None

    slug      = _slugify(project_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"proposal_{slug}_{timestamp}.pdf"
    filepath  = _OUTPUT_DIR / filename

    pdf = _ProposalPDF(doc_title=project_name, client_name=client_name)
    pdf.add_page()
    _render_markdown(pdf, proposal_text)
    pdf.output(str(filepath))

    return str(filepath)


async def generate_all_documents_async(
    proposal_text: str,
    project_name:  str,
    client_name:   str,
) -> dict[str, str | None]:
    """
    Generate all project documents concurrently.

    Runs PDF generation in a thread pool executor so it doesn't block the
    async event loop.  Additional document types (contract, timeline) can be
    added here and they'll all run in parallel via asyncio.gather.

    Returns:
        {
          "proposal_pdf":  "/tmp/creativeops_docs/proposal_<slug>.pdf" | None,
          "proposal_file": "proposal_<slug>.pdf"   (basename for download URL),
        }
    """
    loop = asyncio.get_event_loop()

    proposal_path = await loop.run_in_executor(
        None,
        generate_proposal_pdf,
        proposal_text,
        project_name,
        client_name,
    )

    result: dict[str, str | None] = {
        "proposal_pdf":  proposal_path,
        "proposal_file": Path(proposal_path).name if proposal_path else None,
    }

    return result
