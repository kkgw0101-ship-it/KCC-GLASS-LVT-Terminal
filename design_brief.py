"""Customer-facing KCC Glass LVT design signal PDF generator."""

from __future__ import annotations

import html
import os
from datetime import date, datetime
from io import BytesIO

import pandas as pd
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#172D7C")
KCC_RED = colors.HexColor("#E30613")
GOLD = colors.HexColor("#C8A33B")
INK = colors.HexColor("#24272D")
MUTED = colors.HexColor("#6D727B")
SOFT = colors.HexColor("#F2F4F8")
PALE_BLUE = colors.HexColor("#EEF1F9")
PALE_GOLD = colors.HexColor("#F8F2E2")
LINE = colors.HexColor("#D9DCE3")
WHITE = colors.white


def _plain_text(value):
    text = str(value or "")
    replacements = {
        "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
        "\u2013": "-", "\u2014": "-", "\u2011": "-", "\u00a0": " ",
        "\u2026": "...", "\u2192": "to", "\u00b7": "|",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _escape(value):
    return html.escape(_plain_text(value))


def _short(value, length=90):
    text = " ".join(str(value or "").split())
    return text if len(text) <= length else text[: length - 1].rstrip() + "..."


def _date_label(value, fallback="N/A"):
    if value is None:
        return fallback
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(value).strftime("%b %d, %Y")
    try:
        return pd.Timestamp(value).strftime("%b %d, %Y")
    except Exception:
        return str(value or fallback)


def _frame(value, columns=None):
    if isinstance(value, pd.DataFrame):
        return value.copy()
    if isinstance(value, list):
        return pd.DataFrame(value)
    return pd.DataFrame(columns=columns or [])


def _styles():
    styles = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DesignTitle", parent=styles["Title"], fontName="Helvetica-Bold",
            fontSize=28, leading=31, textColor=NAVY, spaceAfter=3 * mm,
        ),
        "subtitle": ParagraphStyle(
            "DesignSubtitle", parent=styles["BodyText"], fontName="Helvetica",
            fontSize=10.5, leading=14, textColor=MUTED, spaceAfter=3 * mm,
        ),
        "eyebrow": ParagraphStyle(
            "DesignEyebrow", parent=styles["BodyText"], fontName="Helvetica-Bold",
            fontSize=8.5, leading=10, textColor=KCC_RED, spaceAfter=2 * mm,
        ),
        "h2": ParagraphStyle(
            "DesignH2", parent=styles["Heading2"], fontName="Helvetica-Bold",
            fontSize=13, leading=15, textColor=NAVY, spaceBefore=1 * mm, spaceAfter=2 * mm,
        ),
        "h3": ParagraphStyle(
            "DesignH3", parent=styles["Heading3"], fontName="Helvetica-Bold",
            fontSize=9.5, leading=12, textColor=NAVY, spaceAfter=1.2 * mm,
        ),
        "body": ParagraphStyle(
            "DesignBody", parent=styles["BodyText"], fontName="Helvetica",
            fontSize=8.2, leading=11.2, textColor=INK,
        ),
        "small": ParagraphStyle(
            "DesignSmall", parent=styles["BodyText"], fontName="Helvetica",
            fontSize=6.8, leading=9.2, textColor=MUTED,
        ),
        "tiny": ParagraphStyle(
            "DesignTiny", parent=styles["BodyText"], fontName="Helvetica",
            fontSize=5.9, leading=7.5, textColor=MUTED,
        ),
        "card_k": ParagraphStyle(
            "DesignCardK", parent=styles["BodyText"], fontName="Helvetica-Bold",
            fontSize=6.8, leading=8, textColor=KCC_RED, spaceAfter=1.5 * mm,
        ),
        "card_v": ParagraphStyle(
            "DesignCardV", parent=styles["BodyText"], fontName="Helvetica-Bold",
            fontSize=12, leading=14, textColor=NAVY, spaceAfter=1.3 * mm,
        ),
        "card_d": ParagraphStyle(
            "DesignCardD", parent=styles["BodyText"], fontName="Helvetica",
            fontSize=7.2, leading=9.6, textColor=INK,
        ),
        "right": ParagraphStyle(
            "DesignRight", parent=styles["BodyText"], fontName="Helvetica",
            fontSize=7.2, leading=9, textColor=MUTED, alignment=TA_RIGHT,
        ),
        "white": ParagraphStyle(
            "DesignWhite", parent=styles["BodyText"], fontName="Helvetica-Bold",
            fontSize=8, leading=10, textColor=WHITE,
        ),
    }


def _section_head(number, title, styles):
    number_cell = Table(
        [[Paragraph(_escape(number), styles["white"])]],
        colWidths=[12 * mm], rowHeights=[8 * mm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), KCC_RED),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
        ]),
    )
    title_cell = Table(
        [[Paragraph(_escape(title), styles["h2"])]],
        colWidths=[164 * mm], rowHeights=[8 * mm],
        style=TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 1, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
        ]),
    )
    return Table([[number_cell, title_cell]], colWidths=[12 * mm, 164 * mm], hAlign="LEFT")


def _callout(text, styles, color=PALE_BLUE):
    return Table(
        [[Paragraph(_escape(text), styles["body"])]],
        colWidths=[176 * mm],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), color),
            ("LINEBEFORE", (0, 0), (0, -1), 3, NAVY),
            ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5 * mm),
        ]),
    )


def _signal_cards(cards, styles):
    cells = []
    for index, card in enumerate(cards, 1):
        cells.append([
            Paragraph(f"0{index}", styles["card_k"]),
            Paragraph(_escape(card[0]), styles["card_v"]),
            Paragraph(_escape(card[1]), styles["card_d"]),
        ])
    nested = []
    for card in cells:
        nested.append(Table(
            [[card[0]], [card[1]], [card[2]]],
            colWidths=[55 * mm], rowHeights=[5 * mm, 11 * mm, 18 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5 * mm),
            ]),
        ))
    return Table([nested], colWidths=[58.5 * mm] * 3, hAlign="LEFT")


def _bar_chart(rows, width=500, height=165, color=NAVY):
    drawing = Drawing(width, height)
    rows = [(str(label), float(value)) for label, value in rows if pd.notna(value)]
    if not rows:
        drawing.add(String(width / 2, height / 2, "No design signals available", textAnchor="middle", fillColor=MUTED, fontSize=8))
        return drawing
    rows = rows[:8]
    max_value = max(value for _, value in rows) or 1
    left = 112
    right = 28
    top = 15
    row_height = (height - top - 14) / len(rows)
    bar_max = width - left - right
    for index, (label, value) in enumerate(rows):
        y = height - top - (index + 1) * row_height + row_height * 0.23
        drawing.add(String(left - 6, y + 2, _short(label, 21), textAnchor="end", fillColor=MUTED, fontName="Helvetica", fontSize=7.2))
        drawing.add(Rect(left, y, bar_max, row_height * 0.46, fillColor=colors.HexColor("#E7EAF1"), strokeColor=None))
        drawing.add(Rect(left, y, bar_max * value / max_value, row_height * 0.46, fillColor=color, strokeColor=None))
        drawing.add(String(left + bar_max * value / max_value + 5, y + 2, f"{value:g}", fillColor=INK, fontName="Helvetica-Bold", fontSize=7))
    drawing.add(Line(left, 6, width - right, 6, strokeColor=LINE, strokeWidth=0.6))
    return drawing


def _table(data, widths, styles, header=True, font_size=7.1):
    rows = []
    for ridx, row in enumerate(data):
        rendered = []
        for value in row:
            style = styles["white"] if header and ridx == 0 else ParagraphStyle(
                f"Cell{ridx}{len(rendered)}", parent=styles["body"], fontSize=font_size,
                leading=font_size + 2.2, textColor=INK,
            )
            rendered.append(value if hasattr(value, "wrap") else Paragraph(str(value), style))
        rows.append(rendered)
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
    ]
    if header:
        commands.extend([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ])
        start = 1
    else:
        start = 0
    for row in range(start, len(rows)):
        if row % 2 == 0:
            commands.append(("BACKGROUND", (0, row), (-1, row), SOFT))
    return Table(rows, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT", style=TableStyle(commands))


def _fit_image(path, max_width, max_height):
    if not path or not os.path.isfile(path):
        return None
    image = Image(path)
    ratio = min(max_width / image.imageWidth, max_height / image.imageHeight)
    image.drawWidth = image.imageWidth * ratio
    image.drawHeight = image.imageHeight * ratio
    return image


def _taxonomy_top(taxonomy_df, axis, count=3):
    if taxonomy_df.empty or not {"Axis", "Trend Bucket", "Signal"}.issubset(taxonomy_df.columns):
        return []
    subset = taxonomy_df[taxonomy_df["Axis"] == axis].copy()
    subset["Signal"] = pd.to_numeric(subset["Signal"], errors="coerce").fillna(0)
    return list(subset.sort_values("Signal", ascending=False).head(count)[["Trend Bucket", "Signal"]].itertuples(index=False, name=None))


def _default_view(top_keyword, material, pattern, region):
    return (
        f"Recent trade coverage points to {top_keyword.lower()} as a recurring design conversation, "
        f"with {material.lower()} references and {pattern.lower()} treatments providing a practical visual direction. "
        f"For {region}, these signals are best used as an assortment discussion starter rather than a demand forecast. "
        "KCC Glass can translate the themes into selectable visuals, formats and performance specifications through its official LVT design library."
    )


def _external_implication(trend):
    mapping = {
        "warm wood": "Explore warm oak and natural wood colorways for approachable residential stories.",
        "wide plank": "Review longer and wider plank formats where room scale and channel preference support them.",
        "matte finish": "Use low-gloss surfaces and realistic texture to reinforce a natural material impression.",
        "stone look": "Build a focused mineral and stone visual set for commercial and hospitality discussions.",
        "commercial neutral": "Consider restrained greige and taupe palettes for office and retail specifications.",
        "biophilic": "Connect organic grain, natural color and wellbeing-oriented interior narratives.",
        "sustainable": "Pair the visual story with verified material, manufacturing and supply-chain messages.",
        "rigid core": "Present design quality together with the relevant rigid-core performance proposition.",
        "performance": "Explain durability, water resistance and maintenance alongside the visual direction.",
        "texture": "Use embossing and grain alignment to demonstrate tactile and visual differentiation.",
    }
    return mapping.get(str(trend).lower(), "Review the signal as a candidate for color, pattern and surface development.")


def create_customer_design_signal_pdf(ctx, config, logo_path=None, hero_path=None):
    """Create a four-page, externally shareable LVT design signal brief."""
    buffer = BytesIO()
    styles = _styles()
    items = list(ctx.get("items") or [])
    keyword_df = _frame(ctx.get("keywords"), ["Keyword", "Mentions"])
    taxonomy_df = _frame(ctx.get("taxonomy"), ["Axis", "Trend Bucket", "Signal"])
    implication_df = _frame(ctx.get("implications"), ["Trend", "Signal", "Product Implication"])
    source_df = _frame(ctx.get("source_keywords"), ["Source", "Keyword", "Mentions"])
    meta = dict(ctx.get("meta") or {})

    if not keyword_df.empty:
        keyword_df["Mentions"] = pd.to_numeric(keyword_df["Mentions"], errors="coerce").fillna(0)
        keyword_df = keyword_df.sort_values("Mentions", ascending=False)
    top_keyword = str(keyword_df.iloc[0]["Keyword"]) if not keyword_df.empty else "Design performance"
    material_rows = _taxonomy_top(taxonomy_df, "Material")
    color_rows = _taxonomy_top(taxonomy_df, "Color")
    pattern_rows = _taxonomy_top(taxonomy_df, "Pattern")
    material = str(material_rows[0][0]) if material_rows else "Wood"
    pattern = str(pattern_rows[0][0]) if pattern_rows else "Realistic Texture"
    region = str(config.get("region") or "North America")
    issue = str(config.get("issue") or "01").zfill(2)
    report_date = config.get("report_date") or date.today()
    prepared_by = str(config.get("prepared_by") or "KCC Glass PL/LVT Export Sales Team")
    contact = str(config.get("contact") or "")
    kcc_view = str(config.get("kcc_view") or "").strip() or _default_view(top_keyword, material, pattern, region)
    design_library_url = str(config.get("design_library_url") or "https://www.homecc.com/lvt/designlibrary.do")
    data_asof = str(config.get("data_asof") or meta.get("published_end") or "N/A")

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=25 * mm,
        bottomMargin=17 * mm,
        title="KCC Glass LVT Design Signal",
        author=prepared_by,
        subject="Customer-facing LVT design intelligence brief",
    )

    def page_chrome(canvas, document):
        canvas.saveState()
        if logo_path and os.path.isfile(logo_path):
            canvas.drawImage(logo_path, 17 * mm, 281.5 * mm, width=31 * mm, height=8.5 * mm, preserveAspectRatio=True, anchor="sw", mask="auto")
        else:
            canvas.setFillColor(NAVY)
            canvas.setFont("Helvetica-Bold", 13)
            canvas.drawString(17 * mm, 284 * mm, "KCC GLASS")
        canvas.setStrokeColor(NAVY)
        canvas.setLineWidth(0.8)
        canvas.line(17 * mm, 279 * mm, 193 * mm, 279 * mm)
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(17 * mm, 10 * mm, "KCC Glass Market Intelligence | Customer discussion material")
        canvas.drawRightString(193 * mm, 10 * mm, f"{document.page}")
        canvas.restoreState()

    story = []

    # Page 1: Executive signals
    meta_table = Table(
        [[Paragraph("", styles["body"]), Paragraph(
            f"PL / LVT Export Sales<br/>Design Intelligence Series<br/>Issue #{issue} · {_date_label(report_date)}",
            styles["right"],
        )]],
        colWidths=[112 * mm, 64 * mm],
    )
    story.extend([
        meta_table,
        Spacer(1, 3 * mm),
        Paragraph(f"{_escape(region.upper())} FLOORING DESIGN BRIEF", styles["eyebrow"]),
        Paragraph("LVT Design Signal", styles["title"]),
        Paragraph("A concise read on the material, color and pattern signals shaping current flooring conversations.", styles["subtitle"]),
        Paragraph(
            f"Prepared by {_escape(prepared_by)} &nbsp; | &nbsp; Data as of {_escape(data_asof)} &nbsp; | &nbsp; "
            f"Sample: {int(meta.get('sample_count', len(items)))} recent trade articles",
            styles["small"],
        ),
        Spacer(1, 3 * mm),
        _callout(
            "This brief translates public trade coverage into customer discussion themes. It is a directional design reference, not a demand forecast or a claim that every signal applies to every channel.",
            styles,
        ),
        Spacer(1, 5 * mm),
        Paragraph("Executive Design Signals", styles["h2"]),
        _signal_cards([
            (top_keyword.title(), "The most frequently observed keyword in the current sample."),
            (material, "The leading material reference across the classified article set."),
            (pattern, "The strongest pattern or surface-treatment signal in the sample."),
        ], styles),
        Spacer(1, 5 * mm),
        Paragraph("Keyword Signal Ranking", styles["h2"]),
        _bar_chart(list(keyword_df.head(8)[["Keyword", "Mentions"]].itertuples(index=False, name=None)), height=150, color=GOLD),
        Spacer(1, 1 * mm),
        Paragraph(
            "Reading note: mention counts are based on exact keyword families in article titles and summaries. A high count indicates visibility in the sampled coverage, not market share.",
            styles["small"],
        ),
        PageBreak(),
    ])

    # Page 2: Evidence
    source_counts = meta.get("source_counts") or {}
    story.extend([
        _section_head("01", "Trend Evidence", styles),
        Spacer(1, 4 * mm),
        _callout(
            f"The current sample contains {int(source_counts.get('FCW', 0))} FCW and {int(source_counts.get('FCNews', 0))} FCNews articles. "
            f"The published-date range is {meta.get('published_start', 'N/A')} to {meta.get('published_end', 'N/A')}.",
            styles,
        ),
        Spacer(1, 5 * mm),
        Paragraph("Signal by Source", styles["h2"]),
    ])
    source_rows = []
    if not source_df.empty and {"Source", "Keyword", "Mentions"}.issubset(source_df.columns):
        for source in ["FCW", "FCNews"]:
            subset = source_df[source_df["Source"] == source].copy()
            subset["Mentions"] = pd.to_numeric(subset["Mentions"], errors="coerce").fillna(0)
            top = subset.sort_values("Mentions", ascending=False).head(4)
            source_rows.append([
                source,
                ", ".join(f"{row['Keyword']} ({int(row['Mentions'])})" for _, row in top.iterrows()) or "No classified signals",
            ])
    story.extend([
        _table([["Source", "Leading classified keywords"]] + source_rows, [32 * mm, 144 * mm], styles),
        Spacer(1, 5 * mm),
        Paragraph("Selected Public Evidence", styles["h2"]),
    ])
    article_rows = [["Date", "Source", "Article evidence"]]
    for item in items[:7]:
        title = _escape(_short(item.get("title"), 105))
        link = _escape(item.get("link", ""))
        title_para = Paragraph(f'<a href="{link}" color="#172D7C"><u>{title}</u></a>', styles["body"]) if link else Paragraph(title, styles["body"])
        article_rows.append([
            _escape(item.get("published") or "Latest"),
            _escape(item.get("source_group") or item.get("source") or "Source"),
            title_para,
        ])
    story.extend([
        _table(article_rows, [29 * mm, 25 * mm, 122 * mm], styles, font_size=6.7),
        Spacer(1, 4 * mm),
        Paragraph(
            "Source discipline: article titles and links are provided for verification. The report does not reproduce third-party article images or full article text.",
            styles["small"],
        ),
        PageBreak(),
    ])

    # Page 3: Translation
    story.extend([
        _section_head("02", "From Trade Signals to Product Conversation", styles),
        Spacer(1, 4 * mm),
    ])
    hero = _fit_image(hero_path, 176 * mm, 57 * mm)
    if hero:
        story.extend([hero, Spacer(1, 4 * mm)])
    story.append(Paragraph("Material, Color and Pattern Direction", styles["h2"]))
    taxonomy_rows = [["Design axis", "Leading references", "How to read it"]]
    taxonomy_rows.extend([
        ["Material", ", ".join(f"{name} ({int(score)})" for name, score in material_rows) or "N/A", "Use as the visual starting point for assortment discussion."],
        ["Color", ", ".join(f"{name} ({int(score)})" for name, score in color_rows) or "N/A", "Translate the palette into channel-appropriate light, warm or neutral options."],
        ["Pattern", ", ".join(f"{name} ({int(score)})" for name, score in pattern_rows) or "N/A", "Connect surface realism and format to the intended installation context."],
    ])
    story.extend([
        _table(taxonomy_rows, [28 * mm, 78 * mm, 70 * mm], styles),
        Spacer(1, 5 * mm),
        Paragraph("Product Translation", styles["h2"]),
    ])
    implication_rows = [["Signal", "Observed", "Customer discussion translation"]]
    if not implication_df.empty:
        for _, row in implication_df.head(6).iterrows():
            trend = str(row.get("Trend", ""))
            implication_rows.append([
                _escape(trend.title()),
                str(int(float(row.get("Signal", 0) or 0))),
                _escape(_external_implication(trend)),
            ])
    story.extend([
        _table(implication_rows, [34 * mm, 22 * mm, 120 * mm], styles, font_size=6.8),
        Spacer(1, 4 * mm),
        _callout(
            "KCC application principle: pair visual relevance with the required format, wear performance and maintenance story. Design visibility alone should not determine the final assortment.",
            styles,
            color=PALE_GOLD,
        ),
        PageBreak(),
    ])

    # Page 4: Customer application
    story.extend([
        _section_head("03", "Customer Conversation Guide", styles),
        Spacer(1, 4 * mm),
        _signal_cards([
            ("Residential", "Lead with livable wood visuals, warmth and easy-care surface realism."),
            ("Multifamily", "Balance neutral design breadth with repeatability, availability and maintenance needs."),
            ("Commercial", "Translate material cues into durable, specification-ready palettes and formats."),
        ], styles),
        Spacer(1, 6 * mm),
        Paragraph("Suggested Discussion Sequence", styles["h2"]),
        _table([
            ["Step", "Customer question", "Purpose"],
            ["01", "Which visual direction best matches the target channel and end-user?", "Frame the desired material and color story."],
            ["02", "Which formats, constructions and performance attributes are non-negotiable?", "Separate aesthetic preference from specification needs."],
            ["03", "Which two or three options should move into sampling or room-scene review?", "Convert broad trend interest into a manageable shortlist."],
        ], [18 * mm, 101 * mm, 57 * mm], styles),
        Spacer(1, 6 * mm),
        Paragraph("KCC Design View", styles["h2"]),
        _callout(kcc_view, styles),
        Spacer(1, 6 * mm),
        Paragraph("Official KCC LVT Design Library", styles["h2"]),
        Table(
            [[
                Paragraph(
                    "Use the official library to review selectable patterns and build a focused customer presentation from the themes in this brief.",
                    styles["body"],
                ),
                Paragraph(f'<a href="{_escape(design_library_url)}" color="#172D7C"><u>Open Design Library</u></a>', styles["h3"]),
            ]],
            colWidths=[125 * mm, 51 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 4 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
            ]),
        ),
        Spacer(1, 6 * mm),
        HRFlowable(width="100%", thickness=0.7, color=LINE),
        Spacer(1, 3 * mm),
        Paragraph(
            "Methodology and disclaimer. Signals are rule-based counts from a bounded sample of recent FCW and Floor Covering News titles and summaries. "
            "They indicate visibility in public trade coverage and may change as source pages are updated. This document is provided for discussion only and does not constitute a market forecast, product commitment or commercial offer. "
            + (f"Contact: {_escape(contact)}" if contact else "Please contact your KCC Glass representative for product availability and specifications."),
            styles["small"],
        ),
    ])

    doc.build(story, onFirstPage=page_chrome, onLaterPages=page_chrome)
    buffer.seek(0)
    return buffer
