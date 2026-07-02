"""
Reusable PDF formatter — turns a topic + plain-text guide content (pasted
back from the user's own ChatGPT/Claude session) into a styled, downloadable
PDF. This is the shared engine behind generate_guide.py's sample output;
here it's generalized to accept arbitrary pasted text instead of one
hardcoded topic, since app.py needs to format whatever content a user pastes
back from their own AI session.

Heading detection is heuristic, not a full Markdown parser, on purpose —
most people will paste plain text or lightly-formatted Markdown out of
ChatGPT/Claude, and this covers the common cases without adding a
dependency:
  - a line starting with '#' (Markdown heading)
  - a line starting with 'Day ', 'Chapter ', 'Step ', 'Part '
  - a short line (<65 chars) that's title-cased and has no ending period
Everything else is treated as a body paragraph.
"""

import io
import re

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.enums import TA_CENTER

_HEADING_PREFIXES = ("day ", "chapter ", "step ", "part ")


def _get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverTitle2", fontSize=26, leading=32, alignment=TA_CENTER,
                               textColor=colors.HexColor("#14213D"), spaceAfter=14, fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="CoverSub2", fontSize=13, leading=19, alignment=TA_CENTER,
                               textColor=colors.HexColor("#495867"), fontName="Helvetica"))
    styles.add(ParagraphStyle(name="Heading2c", fontSize=16, leading=21, spaceBefore=16, spaceAfter=8,
                               textColor=colors.HexColor("#14213D"), fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Body2", fontSize=10.5, leading=15.5, spaceAfter=8, fontName="Helvetica"))
    return styles


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return True
    lowered = stripped.lower()
    if lowered.startswith(_HEADING_PREFIXES):
        return True
    if len(stripped) < 65 and not stripped.endswith(".") and stripped[0].isupper():
        # crude title-case check: most words start uppercase
        words = stripped.split()
        capitalized = sum(1 for w in words if w[:1].isupper())
        if words and capitalized / len(words) > 0.6:
            return True
    return False


def build_pdf(topic: str, subtitle: str, raw_text: str) -> bytes:
    """Returns the finished PDF as bytes (write to disk or hand to a
    Streamlit st.download_button — no temp file required)."""
    styles = _get_styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                             topMargin=0.9 * inch, bottomMargin=0.9 * inch,
                             leftMargin=0.85 * inch, rightMargin=0.85 * inch)
    story = []

    # Cover
    story.append(Spacer(1, 2.0 * inch))
    story.append(Paragraph(topic, styles["CoverTitle2"]))
    if subtitle:
        story.append(Paragraph(subtitle, styles["CoverSub2"]))
    story.append(PageBreak())

    # Body — split pasted text into heading/paragraph flow
    for raw_line in raw_text.splitlines():
        line = raw_line.strip().lstrip("#").strip()
        if not line:
            continue
        if _looks_like_heading(raw_line):
            story.append(Paragraph(line, styles["Heading2c"]))
        else:
            # escape characters reportlab's mini-XML would choke on
            safe = re.sub(r"&(?!amp;)", "&amp;", line).replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe, styles["Body2"]))

    doc.build(story)
    return buf.getvalue()


def build_ai_prompt(topic: str, reasons: list[str]) -> str:
    """Generates the copy-paste prompt shown to the user for Day/Chapter-style
    guide content, seeded with the real reasons this topic scored well —
    that context measurably improves what ChatGPT/Claude gives back."""
    reason_block = "\n".join(f"- {r}" for r in reasons) if reasons else "- General audience demand."
    return f"""Write a complete, practical PDF guide on the topic: "{topic}".

Context on why this topic was chosen (use it to make the guide specific, not generic):
{reason_block}

Structure it as:
1. A short intro (2-3 sentences) naming the specific problem this solves.
2. 4-6 clearly labeled sections (e.g. "Day 1 — ...", "Step 1 — ...") each with
   practical, specific advice — no filler, no generic platitudes.
3. A short closing section.

Write in plain text with clear section headings on their own line. Avoid
markdown tables. Aim for 800-1200 words total — long enough to be worth
paying for, short enough to actually be read."""
