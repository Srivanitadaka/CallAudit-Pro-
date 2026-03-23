# reports/pdf_report.py
"""
PDF Report Generator
─────────────────────────────────────────────
Generates a professional PDF report for any scored call.

Usage:
  from reports.pdf_report import generate_pdf
  pdf_bytes = generate_pdf(scored_result, filename="call_01.mp3")
"""

import io
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer,
    Table, TableStyle, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT


# ── Colours ────────────────────────────────────────────
C_BG       = colors.HexColor("#080c14")
C_SURFACE  = colors.HexColor("#0d1320")
C_ACCENT   = colors.HexColor("#38bdf8")
C_GREEN    = colors.HexColor("#22c55e")
C_YELLOW   = colors.HexColor("#f59e0b")
C_ORANGE   = colors.HexColor("#fb923c")
C_RED      = colors.HexColor("#f87171")
C_MUTED    = colors.HexColor("#64748b")
C_TEXT     = colors.HexColor("#e2e8f0")
C_WHITE    = colors.white
C_BLACK    = colors.HexColor("#111827")

GRADE_COLORS = {
    "A": C_GREEN,
    "B": C_ACCENT,
    "C": C_YELLOW,
    "D": C_ORANGE,
    "F": C_RED,
}


def _score_color(score, max_val=100):
    pct = score / max_val
    if pct >= 0.75: return C_GREEN
    if pct >= 0.55: return C_YELLOW
    return C_RED


def _sev_color(severity):
    return {
        "critical": C_RED,
        "high":     C_ORANGE,
        "medium":   C_YELLOW,
        "low":      C_MUTED,
    }.get((severity or "").lower(), C_MUTED)


# ══════════════════════════════════════════════════════
# MAIN FUNCTION
# ══════════════════════════════════════════════════════
def generate_pdf(result: dict, filename: str = "call") -> bytes:
    """
    Generate a PDF report for a scored call.
    Returns PDF as bytes — ready to send via Flask.
    """
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize     = A4,
        leftMargin   = 20*mm,
        rightMargin  = 20*mm,
        topMargin    = 20*mm,
        bottomMargin = 20*mm,
    )

    story = []
    W     = A4[0] - 40*mm   # usable width

    # ── Build sections ─────────────────────────────────
    story += _header(result, filename, W)
    story += _overview(result, W)
    story += _dimension_scores(result, W)
    story += _agent_quality(result, W)
    story += _violations(result, W)
    story += _improvements(result, W)
    story += _highlights(result, W)
    story += _summary(result, W)
    story += _footer(W)

    doc.build(story)
    return buffer.getvalue()


# ══════════════════════════════════════════════════════
# SECTION BUILDERS
# ══════════════════════════════════════════════════════

def _header(result, filename, W):
    grade  = result.get("grade", "?")
    score  = result.get("overall_score", 0)
    gc     = GRADE_COLORS.get(grade, C_MUTED)
    now    = datetime.now().strftime("%d %B %Y  %H:%M")

    elements = []

    # Title bar
    title_data = [[
        Paragraph(
            "<font size='18'><b>CallAudit Pro</b></font>"
            "<font size='14' color='#38bdf8'> — Call Quality Report</font>",
            ParagraphStyle("t", fontName="Helvetica-Bold",
                           fontSize=18, textColor=C_WHITE)
        ),
        Paragraph(
            f"<font size='10' color='#64748b'>{now}</font>",
            ParagraphStyle("d", fontName="Helvetica",
                           fontSize=10, textColor=C_MUTED,
                           alignment=TA_RIGHT)
        )
    ]]
    title_tbl = Table(title_data, colWidths=[W*0.65, W*0.35])
    title_tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,-1), C_BG),
        ("TOPPADDING",  (0,0), (-1,-1), 12),
        ("BOTTOMPADDING",(0,0),(-1,-1), 12),
        ("LEFTPADDING", (0,0), (-1,-1), 14),
        ("RIGHTPADDING",(0,0), (-1,-1), 14),
        ("ROUNDEDCORNERS", (0,0), (-1,-1), [6,6,6,6]),
    ]))
    elements.append(title_tbl)
    elements.append(Spacer(1, 8))

    # File info bar
    info_data = [[
        Paragraph(
            f"<font size='11' color='#94a3b8'>File: </font>"
            f"<font size='11' color='#e2e8f0'><b>{filename}</b></font>",
            ParagraphStyle("fi", fontName="Helvetica",
                           fontSize=11, textColor=C_TEXT)
        ),
        Paragraph(
            f"<font size='11' color='#94a3b8'>Outcome: </font>"
            f"<font size='11' color='#e2e8f0'>"
            f"<b>{result.get('call_outcome','Unknown')}</b></font>",
            ParagraphStyle("fo", fontName="Helvetica",
                           fontSize=11, textColor=C_TEXT,
                           alignment=TA_CENTER)
        ),
        Paragraph(
            f"<font size='24' color='{gc.hexval() if hasattr(gc,'hexval') else '#38bdf8'}'>"
            f"<b>Grade {grade}</b></font>",
            ParagraphStyle("fg", fontName="Helvetica-Bold",
                           fontSize=22, textColor=gc,
                           alignment=TA_RIGHT)
        ),
    ]]
    info_tbl = Table(info_data, colWidths=[W*0.45, W*0.3, W*0.25])
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), C_SURFACE),
        ("TOPPADDING",   (0,0), (-1,-1), 10),
        ("BOTTOMPADDING",(0,0), (-1,-1), 10),
        ("LEFTPADDING",  (0,0), (-1,-1), 14),
        ("RIGHTPADDING", (0,0), (-1,-1), 14),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
    ]))
    elements.append(info_tbl)
    elements.append(Spacer(1, 14))

    return elements


def _section_title(text):
    return Paragraph(
        f"<font size='10' color='#64748b'><b>{text.upper()}</b></font>",
        ParagraphStyle("st", fontName="Helvetica-Bold",
                       fontSize=10, textColor=C_MUTED,
                       spaceAfter=6)
    )


def _overview(result, W):
    score   = result.get("overall_score", 0)
    grade   = result.get("grade", "?")
    gc      = GRADE_COLORS.get(grade, C_MUTED)
    sc      = _score_color(score)
    sat     = result.get("satisfaction", {})
    rating  = sat.get("rating", 0)
    sent    = sat.get("sentiment", "neutral")
    frust   = sat.get("customer_frustration", "None")
    stab    = sat.get("emotional_stability", "—")
    resolved = "✔ Resolved" if result.get("was_resolved") else "✘ Unresolved"

    elements = [_section_title("Overall Performance")]

    # Score + Grade cards
    cards = [[
        # Score card
        Table([[
            Paragraph(f"<font size='10' color='#64748b'>OVERALL SCORE</font>",
                      ParagraphStyle("cl", fontName="Helvetica",
                                     fontSize=10, textColor=C_MUTED,
                                     alignment=TA_CENTER)),
        ],[
            Paragraph(f"<font size='32'><b>{score}</b></font>"
                      f"<font size='16' color='#64748b'>/100</font>",
                      ParagraphStyle("cv", fontName="Helvetica-Bold",
                                     fontSize=32, textColor=sc,
                                     alignment=TA_CENTER)),
        ]], colWidths=[W*0.3]),

        # Grade card
        Table([[
            Paragraph(f"<font size='10' color='#64748b'>GRADE</font>",
                      ParagraphStyle("gl", fontName="Helvetica",
                                     fontSize=10, textColor=C_MUTED,
                                     alignment=TA_CENTER)),
        ],[
            Paragraph(f"<font size='36'><b>{grade}</b></font>",
                      ParagraphStyle("gv", fontName="Helvetica-Bold",
                                     fontSize=36, textColor=gc,
                                     alignment=TA_CENTER)),
        ]], colWidths=[W*0.2]),

        # Satisfaction card
        Table([[
            Paragraph(f"<font size='10' color='#64748b'>SATISFACTION</font>",
                      ParagraphStyle("sl", fontName="Helvetica",
                                     fontSize=10, textColor=C_MUTED,
                                     alignment=TA_CENTER)),
        ],[
            Paragraph(f"<font size='28'><b>{rating:.1f}</b></font>"
                      f"<font size='14' color='#64748b'>/5</font>",
                      ParagraphStyle("sv", fontName="Helvetica-Bold",
                                     fontSize=28,
                                     textColor=_score_color(rating,5),
                                     alignment=TA_CENTER)),
        ]], colWidths=[W*0.25]),

        # Outcome card
        Table([[
            Paragraph(f"<font size='10' color='#64748b'>OUTCOME</font>",
                      ParagraphStyle("ol", fontName="Helvetica",
                                     fontSize=10, textColor=C_MUTED,
                                     alignment=TA_CENTER)),
        ],[
            Paragraph(f"<font size='13'><b>{resolved}</b></font>",
                      ParagraphStyle("ov", fontName="Helvetica-Bold",
                                     fontSize=13,
                                     textColor=C_GREEN if result.get("was_resolved") else C_RED,
                                     alignment=TA_CENTER)),
        ]], colWidths=[W*0.25]),
    ]]

    overview_tbl = Table(cards, colWidths=[W*0.3, W*0.2, W*0.25, W*0.25])
    overview_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), C_SURFACE),
        ("TOPPADDING",   (0,0), (-1,-1), 14),
        ("BOTTOMPADDING",(0,0), (-1,-1), 14),
        ("LEFTPADDING",  (0,0), (-1,-1), 8),
        ("RIGHTPADDING", (0,0), (-1,-1), 8),
        ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ("LINEAFTER",    (0,0), (2,0), 0.5, C_BLACK),
    ]))
    elements.append(overview_tbl)
    elements.append(Spacer(1, 6))

    # Satisfaction details row
    sat_data = [[
        Paragraph(f"<font size='10' color='#64748b'>Sentiment: </font>"
                  f"<font size='10'><b>{sent.title()}</b></font>",
                  ParagraphStyle("sd", fontName="Helvetica", fontSize=10, textColor=C_TEXT)),
        Paragraph(f"<font size='10' color='#64748b'>Frustration: </font>"
                  f"<font size='10'><b>{frust}</b></font>",
                  ParagraphStyle("fd", fontName="Helvetica", fontSize=10, textColor=C_TEXT)),
        Paragraph(f"<font size='10' color='#64748b'>Stability: </font>"
                  f"<font size='10'><b>{stab}</b></font>",
                  ParagraphStyle("stb", fontName="Helvetica", fontSize=10, textColor=C_TEXT)),
        Paragraph(f"<font size='10' color='#64748b'>Issue: </font>"
                  f"<font size='10'><b>{str(result.get('issue_detected',''))[:50]}</b></font>",
                  ParagraphStyle("id", fontName="Helvetica", fontSize=10, textColor=C_TEXT)),
    ]]
    sat_tbl = Table(sat_data, colWidths=[W*0.25]*4)
    sat_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,-1), C_BLACK),
        ("TOPPADDING",   (0,0), (-1,-1), 8),
        ("BOTTOMPADDING",(0,0), (-1,-1), 8),
        ("LEFTPADDING",  (0,0), (-1,-1), 10),
        ("RIGHTPADDING", (0,0), (-1,-1), 10),
    ]))
    elements.append(sat_tbl)
    elements.append(Spacer(1, 14))
    return elements


def _dimension_scores(result, W):
    dims = result.get("dimension_scores", result.get("scores", {}))
    DIM_LABELS = {
        "empathy":                  "Empathy",
        "professionalism":          "Professionalism",
        "compliance":               "Compliance",
        "resolution_effectiveness": "Resolution",
        "communication_clarity":    "Clarity",
    }

    elements = [_section_title("Dimension Scores")]
    rows     = []

    for key, label in DIM_LABELS.items():
        val    = dims.get(key, 0)
        col    = _score_color(val, 10)
        bar_w  = int((val / 10) * 100)

        # Bar as table cell background trick
        bar_data = [[
            Paragraph(
                f"<font size='10'>{label}</font>",
                ParagraphStyle("dl", fontName="Helvetica",
                               fontSize=10, textColor=C_TEXT)
            ),
            Table([[""]], colWidths=[W*0.45 * val/10],
                  rowHeights=[12]),
            Paragraph(
                f"<font size='11'><b>{val}/10</b></font>",
                ParagraphStyle("dv", fontName="Helvetica-Bold",
                               fontSize=11, textColor=col,
                               alignment=TA_RIGHT)
            ),
        ]]
        row_tbl = Table(bar_data, colWidths=[W*0.2, W*0.6, W*0.2])
        row_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (1,0), (1,0), col),
            ("BACKGROUND",   (0,0), (0,0), C_SURFACE),
            ("BACKGROUND",   (2,0), (2,0), C_SURFACE),
            ("TOPPADDING",   (0,0), (-1,-1), 6),
            ("BOTTOMPADDING",(0,0), (-1,-1), 6),
            ("LEFTPADDING",  (0,0), (0,0), 10),
            ("RIGHTPADDING", (2,0), (2,0), 10),
            ("VALIGN",       (0,0), (-1,-1), "MIDDLE"),
        ]))
        rows.append(row_tbl)
        rows.append(Spacer(1, 4))

    elements += rows
    elements.append(Spacer(1, 10))
    return elements


def _agent_quality(result, W):
    aq = result.get("agent_quality", {})
    if not aq:
        return []

    elements = [_section_title("Agent Quality Assessment")]

    metrics = [
        ("Language Clarity",    aq.get("language_clarity",   0), 20),
        ("Professionalism",     aq.get("professionalism",    0), 20),
        ("Time Efficiency",     aq.get("time_efficiency",    0), 20),
        ("Response Efficiency", aq.get("response_efficiency",0), 20),
        ("Empathy Score",       aq.get("empathy_score",      0), 10),
    ]

    data = [["Metric", "Score", "Max"]]
    for label, val, mx in metrics:
        col = _score_color(val, mx)
        data.append([
            Paragraph(f"<font size='10'>{label}</font>",
                      ParagraphStyle("am", fontName="Helvetica",
                                     fontSize=10, textColor=C_TEXT)),
            Paragraph(f"<font size='10'><b>{val}</b></font>",
                      ParagraphStyle("av", fontName="Helvetica-Bold",
                                     fontSize=10, textColor=col,
                                     alignment=TA_CENTER)),
            Paragraph(f"<font size='10' color='#64748b'>{mx}</font>",
                      ParagraphStyle("ax", fontName="Helvetica",
                                     fontSize=10, textColor=C_MUTED,
                                     alignment=TA_CENTER)),
        ])

    tbl = Table(data, colWidths=[W*0.6, W*0.2, W*0.2])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0,0), (-1,0),  C_BLACK),
        ("BACKGROUND",   (0,1), (-1,-1), C_SURFACE),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [C_SURFACE, C_BLACK]),
        ("TEXTCOLOR",    (0,0), (-1,0),  C_MUTED),
        ("FONTNAME",     (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",     (0,0), (-1,0),  9),
        ("TOPPADDING",   (0,0), (-1,-1), 7),
        ("BOTTOMPADDING",(0,0), (-1,-1), 7),
        ("LEFTPADDING",  (0,0), (-1,-1), 10),
        ("ALIGN",        (1,0), (-1,-1), "CENTER"),
        ("GRID",         (0,0), (-1,-1), 0.3, C_BLACK),
    ]))
    elements.append(tbl)

    # Pills
    bias  = aq.get("bias_detected", False)
    calmed = aq.get("calmed_customer", False)
    pills_text = (
        f"  {'⚠ Bias Detected' if bias else '✔ No Bias'}   "
        f"  {'✔ Customer Calmed' if calmed else '✘ Not Calmed'}"
    )
    elements.append(Spacer(1, 6))
    elements.append(
        Paragraph(
            f"<font size='10' color='#94a3b8'>{pills_text}</font>",
            ParagraphStyle("pills", fontName="Helvetica",
                           fontSize=10, textColor=C_MUTED)
        )
    )
    elements.append(Spacer(1, 14))
    return elements


def _violations(result, W):
    viols = result.get("violations", [])
    elements = [_section_title(f"Policy Violations ({len(viols)})")]

    if not viols:
        elements.append(
            Paragraph(
                "<font size='11' color='#22c55e'>✔ No violations detected</font>",
                ParagraphStyle("nv", fontName="Helvetica",
                               fontSize=11, textColor=C_GREEN)
            )
        )
        elements.append(Spacer(1, 14))
        return elements

    for v in viols:
        sev    = (v.get("severity") or "medium").lower()
        sc     = _sev_color(sev)
        vtype  = (v.get("type") or "").replace("_"," ").title()
        expl   = v.get("explanation", "")[:200]
        quote  = v.get("quote", "")[:150]

        vdata = [[
            Paragraph(
                f"<font size='11'><b>{vtype}</b></font>  "
                f"<font size='9' color='#94a3b8'>[{sev.upper()}]</font>",
                ParagraphStyle("vt", fontName="Helvetica-Bold",
                               fontSize=11, textColor=C_TEXT)
            )
        ],[
            Paragraph(
                f"<font size='10' color='#94a3b8'>{expl}</font>",
                ParagraphStyle("ve", fontName="Helvetica",
                               fontSize=10, textColor=C_MUTED)
            )
        ]]

        if quote:
            vdata.append([
                Paragraph(
                    f"<font size='9' color='#f87171'>\"{quote}\"</font>",
                    ParagraphStyle("vq", fontName="Helvetica-Oblique",
                                   fontSize=9, textColor=C_RED)
                )
            ])

        vtbl = Table(vdata, colWidths=[W])
        vtbl.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,-1), C_SURFACE),
            ("LEFTPADDING",  (0,0), (-1,-1), 14),
            ("RIGHTPADDING", (0,0), (-1,-1), 10),
            ("TOPPADDING",   (0,0), (-1,-1), 8),
            ("BOTTOMPADDING",(0,0), (-1,-1), 8),
            ("LINEBEFOREE",  (0,0), (0,-1), 4, sc),
        ]))

        # Left color bar via outer table
        outer = Table([[
            Table([[""]], colWidths=[4], rowHeights=[None]),
            vtbl
        ]], colWidths=[4, W])
        outer.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (0,-1), sc),
            ("TOPPADDING",   (0,0), (-1,-1), 0),
            ("BOTTOMPADDING",(0,0), (-1,-1), 0),
            ("LEFTPADDING",  (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ]))

        elements.append(outer)
        elements.append(Spacer(1, 6))

    elements.append(Spacer(1, 8))
    return elements


def _improvements(result, W):
    imps = result.get("improvements", [])
    elements = [_section_title(f"Coaching Improvements ({len(imps)})")]

    if not imps:
        elements.append(
            Paragraph(
                "<font size='11' color='#22c55e'>✔ No improvements needed</font>",
                ParagraphStyle("ni", fontName="Helvetica",
                               fontSize=11, textColor=C_GREEN)
            )
        )
        elements.append(Spacer(1, 14))
        return elements

    for i in imps:
        area  = (i.get("area") or "").replace("_"," ").title()
        sug   = i.get("suggestion", "")[:200]
        ex    = i.get("example", "")[:150]

        idata = [[
            Paragraph(
                f"<font size='10' color='#38bdf8'><b>{area.upper()}</b></font>",
                ParagraphStyle("ia", fontName="Helvetica-Bold",
                               fontSize=10, textColor=C_ACCENT)
            )
        ],[
            Paragraph(
                f"<font size='10'>{sug}</font>",
                ParagraphStyle("is", fontName="Helvetica",
                               fontSize=10, textColor=C_TEXT)
            )
        ]]

        if ex:
            idata.append([
                Paragraph(
                    f"<font size='9' color='#64748b'>💬 \"{ex}\"</font>",
                    ParagraphStyle("ie", fontName="Helvetica-Oblique",
                                   fontSize=9, textColor=C_MUTED)
                )
            ])

        itbl = Table(idata, colWidths=[W-4])
        itbl.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,-1), C_SURFACE),
            ("LEFTPADDING",  (0,0), (-1,-1), 14),
            ("RIGHTPADDING", (0,0), (-1,-1), 10),
            ("TOPPADDING",   (0,0), (-1,-1), 8),
            ("BOTTOMPADDING",(0,0), (-1,-1), 8),
        ]))

        outer = Table([[
            Table([[""]], colWidths=[4], rowHeights=[None]),
            itbl
        ]], colWidths=[4, W])
        outer.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (0,-1), C_ACCENT),
            ("TOPPADDING",   (0,0), (-1,-1), 0),
            ("BOTTOMPADDING",(0,0), (-1,-1), 0),
            ("LEFTPADDING",  (0,0), (-1,-1), 0),
            ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ]))

        elements.append(outer)
        elements.append(Spacer(1, 6))

    elements.append(Spacer(1, 8))
    return elements


def _highlights(result, W):
    highs = result.get("highlights", [])
    if not highs:
        return []

    elements = [_section_title(f"What Went Well ({len(highs)})")]
    for h in highs:
        elements.append(
            Paragraph(
                f"<font size='10' color='#22c55e'>✅ {h}</font>",
                ParagraphStyle("hi", fontName="Helvetica",
                               fontSize=10, textColor=C_GREEN,
                               leftIndent=10, spaceAfter=4)
            )
        )
    elements.append(Spacer(1, 10))
    return elements


def _summary(result, W):
    summary = result.get("summary", "")
    if not summary:
        return []

    elements = [_section_title("AI Summary")]
    elements.append(
        Paragraph(
            f"<font size='11'>{summary}</font>",
            ParagraphStyle("su", fontName="Helvetica",
                           fontSize=11, textColor=C_TEXT,
                           leading=16,
                           leftIndent=10)
        )
    )
    elements.append(Spacer(1, 14))
    return elements


def _footer(W):
    now = datetime.now().strftime("%d %B %Y %H:%M")
    return [
        HRFlowable(width=W, color=C_BLACK),
        Spacer(1, 6),
        Paragraph(
            f"<font size='9' color='#1e293b'>"
            f"CallAudit Pro · Generated {now} · "
            f"llama-3.3-70b · Groq · LangChain · RAG</font>",
            ParagraphStyle("ft", fontName="Helvetica",
                           fontSize=9, textColor=C_MUTED,
                           alignment=TA_CENTER)
        )
    ]