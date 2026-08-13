"""One-page internal executive brief for U.S. resilient-flooring conditions."""

from __future__ import annotations

import html
import os
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#172D7C")
DEEP_NAVY = colors.HexColor("#101B43")
KCC_RED = colors.HexColor("#E12B2B")
GOLD = colors.HexColor("#E7B94E")
INK = colors.HexColor("#222733")
MUTED = colors.HexColor("#697180")
SOFT = colors.HexColor("#F3F5F8")
PALE_BLUE = colors.HexColor("#EBEFFA")
LINE = colors.HexColor("#D9DEE8")
GREEN = colors.HexColor("#16784B")
AMBER = colors.HexColor("#A46B00")

MODULE_DIR = os.path.dirname(__file__)
REGULAR_FONT_PATH = os.path.join(MODULE_DIR, "NotoSansKR-Regular.ttf")
BOLD_FONT_PATH = os.path.join(MODULE_DIR, "NotoSansKR-Bold.ttf")
if os.path.isfile(REGULAR_FONT_PATH) and os.path.isfile(BOLD_FONT_PATH):
    pdfmetrics.registerFont(TTFont("KCCSans", REGULAR_FONT_PATH))
    pdfmetrics.registerFont(TTFont("KCCSans-Bold", BOLD_FONT_PATH))
    pdfmetrics.registerFontFamily(
        "KCCSans",
        normal="KCCSans",
        bold="KCCSans-Bold",
        italic="KCCSans",
        boldItalic="KCCSans-Bold",
    )
    BODY_FONT = "KCCSans"
    BOLD_FONT = "KCCSans-Bold"
else:
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    BODY_FONT = "HYGothic-Medium"
    BOLD_FONT = "HYGothic-Medium"


def _escape(value):
    return html.escape(str(value or ""))


def _short(value, limit=150):
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "..."


def _styles():
    sample = getSampleStyleSheet()
    return {
        "brand": ParagraphStyle(
            "PulseBrand", parent=sample["Normal"], fontName=BODY_FONT,
            fontSize=7.2, leading=9, textColor=MUTED,
        ),
        "title": ParagraphStyle(
            "PulseTitle", parent=sample["Title"], fontName=BOLD_FONT,
            fontSize=19, leading=22, textColor=NAVY, alignment=TA_LEFT, spaceAfter=1.5 * mm,
        ),
        "subtitle": ParagraphStyle(
            "PulseSubtitle", parent=sample["Normal"], fontName=BODY_FONT,
            fontSize=8, leading=10, textColor=MUTED,
        ),
        "status": ParagraphStyle(
            "PulseStatus", parent=sample["Normal"], fontName=BODY_FONT,
            fontSize=8.3, leading=10.5, textColor=colors.white,
        ),
        "headline": ParagraphStyle(
            "PulseHeadline", parent=sample["Normal"], fontName=BODY_FONT,
            fontSize=12.2, leading=15, textColor=colors.white,
        ),
        "head": ParagraphStyle(
            "PulseHead", parent=sample["Heading2"], fontName=BOLD_FONT,
            fontSize=9.4, leading=11, textColor=NAVY, spaceBefore=1.8 * mm, spaceAfter=1.2 * mm,
        ),
        "body": ParagraphStyle(
            "PulseBody", parent=sample["BodyText"], fontName=BODY_FONT,
            fontSize=7.3, leading=9.6, textColor=INK,
        ),
        "small": ParagraphStyle(
            "PulseSmall", parent=sample["BodyText"], fontName=BODY_FONT,
            fontSize=6.2, leading=7.8, textColor=MUTED,
        ),
        "metric_label": ParagraphStyle(
            "PulseMetricLabel", parent=sample["Normal"], fontName=BODY_FONT,
            fontSize=5.8, leading=7, textColor=MUTED,
        ),
        "metric_value": ParagraphStyle(
            "PulseMetricValue", parent=sample["Normal"], fontName=BOLD_FONT,
            fontSize=9.6, leading=11, textColor=NAVY,
        ),
        "metric_change": ParagraphStyle(
            "PulseMetricChange", parent=sample["Normal"], fontName=BODY_FONT,
            fontSize=5.9, leading=7, textColor=MUTED,
        ),
        "table_head": ParagraphStyle(
            "PulseTableHead", parent=sample["Normal"], fontName=BOLD_FONT,
            fontSize=6.2, leading=7.4, textColor=colors.white,
        ),
        "table": ParagraphStyle(
            "PulseTable", parent=sample["Normal"], fontName=BODY_FONT,
            fontSize=6.1, leading=7.8, textColor=INK,
        ),
    }


def _paragraph(text, style, limit=None):
    value = _short(text, limit) if limit else str(text or "")
    return Paragraph(_escape(value), style)


def _page_chrome(generated_at):
    def draw(canvas, document):
        canvas.saveState()
        canvas.setFillColor(DEEP_NAVY)
        canvas.rect(0, 0, A4[0], 9 * mm, fill=1, stroke=0)
        canvas.setFillColor(colors.white)
        canvas.setFont(BODY_FONT, 6.2)
        canvas.drawString(15 * mm, 3.4 * mm, "KCC Glass LVT Intelligence | Internal executive material")
        canvas.drawRightString(195 * mm, 3.4 * mm, f"Generated {generated_at}  |  {document.page}")
        canvas.restoreState()
    return draw


def _status_color(status):
    text = str(status or "혼조")
    if text in {"압박", "둔화"}:
        return KCC_RED
    if text in {"안정화", "회복"}:
        return GREEN
    return AMBER


def _metric_cards(metrics, styles, available_width):
    cells = []
    for metric in list(metrics or [])[:6]:
        cells.append([
            _paragraph(metric.get("label"), styles["metric_label"], 27),
            _paragraph(metric.get("value"), styles["metric_value"], 18),
            _paragraph(metric.get("change"), styles["metric_change"], 22),
            _paragraph(f"As of {metric.get('asof') or 'N/A'}", styles["metric_change"], 25),
        ])
    while len(cells) < 6:
        cells.append([_paragraph("N/A", styles["metric_label"]), _paragraph("N/A", styles["metric_value"]), "", ""])
    table = Table([cells], colWidths=[available_width / 6] * 6, rowHeights=[22 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _summary_block(analysis, styles):
    bullets = list(analysis.get("executive_summary") or [])[:3]
    if not bullets:
        bullets = [analysis.get("headline") or "분석 결과를 확인할 수 없습니다."]
    return Table(
        [[Paragraph(f"<font color='#E12B2B'>■</font> {_escape(_short(item, 180))}", styles["body"])] for item in bullets],
        colWidths=[176 * mm],
        style=TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 1.4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4),
        ]),
    )


def _drivers_table(analysis, styles):
    header = [
        _paragraph("Driver", styles["table_head"]),
        _paragraph("Direction", styles["table_head"]),
        _paragraph("Article evidence", styles["table_head"]),
        _paragraph("Indicator check / implication", styles["table_head"]),
    ]
    rows = [header]
    direction_map = {"negative": "Negative", "neutral": "Mixed", "positive": "Positive"}
    for driver in list(analysis.get("drivers") or [])[:4]:
        combined = f"{driver.get('indicator_evidence', '')}  |  {driver.get('implication', '')}"
        rows.append([
            _paragraph(driver.get("driver"), styles["table"], 42),
            _paragraph(direction_map.get(driver.get("direction"), driver.get("direction")), styles["table"], 14),
            _paragraph(driver.get("article_evidence"), styles["table"], 120),
            _paragraph(combined, styles["table"], 140),
        ])
    if len(rows) == 1:
        rows.append([_paragraph("N/A", styles["table"]), "", _paragraph("No validated driver output.", styles["table"]), ""])
    table = Table(rows, colWidths=[31 * mm, 20 * mm, 61 * mm, 64 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _channel_and_watch(analysis, styles):
    channel_rows = []
    for item in list(analysis.get("channels") or [])[:3]:
        channel_rows.append([
            _paragraph(item.get("channel"), styles["table"], 35),
            _paragraph(item.get("status"), styles["table"], 12),
            _paragraph(item.get("read"), styles["table"], 95),
        ])
    if not channel_rows:
        channel_rows = [[_paragraph("N/A", styles["table"]), "", _paragraph("No validated channel output.", styles["table"])]]
    channels = Table(channel_rows, colWidths=[26 * mm, 16 * mm, 45 * mm])
    channels.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, SOFT]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    watch_items = list(analysis.get("watch_items") or [])[:3]
    watch = Table(
        [[Paragraph(f"<font color='#172D7C'>•</font> {_escape(_short(item, 105))}", styles["table"])] for item in watch_items]
        or [[_paragraph("No validated watch item.", styles["table"])]],
        colWidths=[85 * mm],
    )
    watch.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE),
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return Table(
        [[
            [Paragraph("Channel read", styles["head"]), channels],
            [Paragraph("Management watch", styles["head"]), watch],
        ]],
        colWidths=[88 * mm, 88 * mm],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
            ("RIGHTPADDING", (0, 0), (0, 0), 3),
            ("LEFTPADDING", (1, 0), (1, 0), 3),
            ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]),
    )


def create_resilient_market_pulse_pdf(analysis, metrics, articles, config=None, logo_path=None):
    """Create a one-page, Korean-language internal executive PDF."""
    if not analysis or not analysis.get("ok"):
        raise ValueError("A validated article analysis is required before PDF generation.")

    config = dict(config or {})
    generated = str(analysis.get("generated_at") or datetime.now().astimezone().isoformat(timespec="minutes"))[:16].replace("T", " ")
    styles = _styles()
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=13 * mm,
        bottomMargin=13 * mm,
        title="U.S. Resilient Market Pulse",
        author="KCC Glass LVT Intelligence",
    )
    usable_width = A4[0] - document.leftMargin - document.rightMargin
    story = []

    if logo_path and os.path.isfile(logo_path):
        logo = Image(logo_path, width=37 * mm, height=10 * mm)
        logo.hAlign = "LEFT"
        brand_left = logo
    else:
        brand_left = Paragraph("<b>KCC GLASS</b>", ParagraphStyle(
            "FallbackLogo", fontName="Helvetica-Bold", fontSize=15, textColor=NAVY,
        ))
    brand_right = Paragraph(
        "INTERNAL MARKET INTELLIGENCE<br/>U.S. RESILIENT FLOORING",
        ParagraphStyle("BrandRight", parent=styles["brand"], alignment=TA_RIGHT),
    )
    brand = Table([[brand_left, brand_right]], colWidths=[105 * mm, 71 * mm])
    brand.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.extend([brand, HRFlowable(width="100%", thickness=1.1, color=NAVY, spaceBefore=1.5 * mm, spaceAfter=2.5 * mm)])

    story.append(Paragraph("U.S. Resilient Market Pulse", styles["title"]))
    story.append(Paragraph(
        f"미국 내수·Resilient 주문 환경 진단  |  "
        f"Method: {_escape(analysis.get('analysis_mode') or 'Unknown')}  |  "
        f"지표 기준일 개별 표기  |  분석 생성 {generated}",
        styles["subtitle"],
    ))
    story.append(Spacer(1, 2.2 * mm))

    verdict = Table([[
        Paragraph(
            f"<b>판정  {_escape(analysis.get('status'))}</b> &nbsp;&nbsp; 신뢰도 {_escape(analysis.get('confidence'))}",
            styles["status"],
        ),
        Paragraph(f"<b>{_escape(_short(analysis.get('headline'), 125))}</b>", styles["headline"]),
    ]], colWidths=[38 * mm, 138 * mm])
    verdict.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), _status_color(analysis.get("status"))),
        ("BACKGROUND", (1, 0), (1, 0), DEEP_NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.extend([verdict, Paragraph("Executive Summary", styles["head"]), _summary_block(analysis, styles)])
    story.extend([Paragraph("Market signal dashboard", styles["head"]), _metric_cards(metrics, styles, usable_width)])
    story.extend([Paragraph("What is constraining orders", styles["head"]), _drivers_table(analysis, styles)])
    story.append(_channel_and_watch(analysis, styles))

    contradictions = list(analysis.get("contradictions") or [])[:2]
    caveat_parts = [_short(analysis.get("caveat"), 180)] + [_short(item, 110) for item in contradictions]
    if analysis.get("analysis_mode") == "Rule-based fallback":
        caveat_parts.insert(
            0,
            f"Rule-based fallback ({analysis.get('fallback_reason') or 'Anthropic API unavailable'})",
        )
    caveat_text = "  ".join(part for part in caveat_parts if part)
    story.append(Spacer(1, 1.8 * mm))
    story.append(Table([[Paragraph(f"<b>해석 유의:</b> {_escape(caveat_text)}", styles["small"])]], colWidths=[176 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF5DD")),
        ("BOX", (0, 0), (-1, -1), 0.4, GOLD),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ])))

    source_lines = []
    for index, article in enumerate(list(articles or [])[:3], 1):
        source_lines.append(
            f"{index}. {_short(article.get('title'), 78)} ({article.get('source')}, {article.get('published') or 'date not stated'})"
        )
    source_note = " | ".join(source_lines) or "No article source metadata available."
    story.append(Paragraph(
        f"<b>Sources:</b> {_escape(source_note)}  |  Indicators: FRED and platform source tables; each metric carries its own as-of date.",
        styles["small"],
    ))

    chrome = _page_chrome(generated)
    document.build(story, onFirstPage=chrome, onLaterPages=chrome)
    buffer.seek(0)
    return buffer
