"""Customer-facing KCC Glass LVT market brief PDF generator."""

from __future__ import annotations

import html
import os
from datetime import date, datetime
from io import BytesIO

import pandas as pd
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Flowable,
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
GOLD = colors.HexColor("#B59A5B")
INK = colors.HexColor("#24272D")
MUTED = colors.HexColor("#6D727B")
SOFT = colors.HexColor("#F2F4F8")
PALE_BLUE = colors.HexColor("#EEF1F9")
LINE = colors.HexColor("#D9DCE3")
LIGHT_GREY = colors.HexColor("#C9CDD4")
PALE_RED = colors.HexColor("#FDE9EA")
PALE_GOLD = colors.HexColor("#F7F0DC")
PALE_GREY = colors.HexColor("#ECEDEF")


class _StatusBadge(Flowable):
    """Compact research-note status badge used in the implications table."""

    def __init__(self, text, fill_color, text_color, width=27 * mm, height=5.2 * mm):
        super().__init__()
        self.text = text
        self.fill_color = fill_color
        self.text_color = text_color
        self.width = width
        self.height = height

    def wrap(self, avail_width, avail_height):
        return min(self.width, avail_width), self.height

    def draw(self):
        self.canv.setFillColor(self.fill_color)
        self.canv.roundRect(0, 0, self.width, self.height, self.height / 2, fill=1, stroke=0)
        self.canv.setFillColor(self.text_color)
        self.canv.setFont("Helvetica-Bold", 6.2)
        self.canv.drawCentredString(self.width / 2, 1.45 * mm, self.text)


def _float(value, default=None):
    try:
        if value is None or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt(value, pattern, default="N/A"):
    value = _float(value)
    return pattern.format(value) if value is not None else default


def _change(value, period="", digits=1):
    value = _float(value)
    if value is None:
        return "N/A"
    prefix = f"{period} " if period else ""
    return f"{prefix}{value:+.{digits}f}%"


def _escape(value):
    return html.escape(str(value or ""))


def _date_label(value, fallback="N/A"):
    if value is None:
        return fallback
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(value).strftime("%b %d, %Y")
    text = str(value)
    try:
        return pd.Timestamp(text).strftime("%b %d, %Y")
    except Exception:
        return text or fallback


def _series_points(df, value_col, periods=8, resample=None):
    if not isinstance(df, pd.DataFrame) or df.empty or value_col not in df.columns:
        return [], []
    data = df.copy()
    if "date" not in data.columns:
        return [], []
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna(subset=["date", value_col]).sort_values("date")
    if data.empty:
        return [], []
    if resample:
        data = data.set_index("date")[[value_col]].resample(resample).last().dropna().reset_index()
    data = data.tail(periods)
    labels = [d.strftime("%b") for d in data["date"]]
    values = data[value_col].astype(float).tolist()
    return labels, values


def _line_chart(labels, series, width=500, height=190, palette=None):
    drawing = Drawing(width, height)
    if not labels or not series or not any(values for _, values in series):
        drawing.add(String(width / 2, height / 2, "Insufficient public data for this chart", textAnchor="middle", fillColor=MUTED, fontSize=9))
        return drawing

    palette = palette or [NAVY, KCC_RED, GOLD]
    values = [v for _, rows in series for v in rows if v is not None]
    low, high = min(values), max(values)
    span = max(high - low, abs(high) * 0.04, 1)

    chart = HorizontalLineChart()
    chart.x = 48
    chart.y = 28
    chart.width = width - 62
    chart.height = height - 52
    chart.data = [rows for _, rows in series]
    chart.joinedLines = 1
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.categoryAxis.labels.fontSize = 7
    chart.categoryAxis.labels.fillColor = MUTED
    chart.categoryAxis.strokeColor = LIGHT_GREY
    chart.valueAxis.valueMin = low - span * 0.10
    chart.valueAxis.valueMax = high + span * 0.13
    chart.valueAxis.valueStep = max(round(span / 4), 1)
    chart.valueAxis.labelTextFormat = "%.0f"
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labels.fillColor = MUTED
    chart.valueAxis.strokeColor = LIGHT_GREY
    chart.valueAxis.gridStrokeColor = colors.HexColor("#E7E9EE")
    chart.valueAxis.visibleGrid = 1
    for i, _ in enumerate(series):
        chart.lines[i].strokeColor = palette[i % len(palette)]
        chart.lines[i].strokeWidth = 2.2 if i == 0 else 1.7
        marker = makeMarker("FilledCircle")
        marker.size = 3.6 if i == 0 else 3.0
        marker.fillColor = palette[i % len(palette)]
        marker.strokeColor = colors.white
        marker.strokeWidth = 0.6
        chart.lines[i].symbol = marker
    drawing.add(chart)

    legend_x = 54
    for i, (name, _) in enumerate(series):
        x = legend_x + i * 118
        drawing.add(String(x, height - 12, "-", fillColor=palette[i % len(palette)], fontName="Helvetica-Bold", fontSize=13))
        drawing.add(String(x + 12, height - 10, name, fillColor=MUTED, fontName="Helvetica", fontSize=7.2))
    return drawing


def _grouped_bar_chart(categories, previous, current, previous_label, current_label, width=500, height=190):
    drawing = Drawing(width, height)
    if not categories or not current:
        drawing.add(String(width / 2, height / 2, "Insufficient public data for this chart", textAnchor="middle", fillColor=MUTED, fontSize=9))
        return drawing
    left, right, baseline, top = 55, 16, 30, height - 40
    plot_width, plot_height = width - left - right, top - baseline
    high = max(previous + current) if previous + current else 1
    high = max(high * 1.16, 1)
    for i in range(5):
        y = baseline + plot_height * i / 4
        drawing.add(Line(left, y, width - right, y, strokeColor=colors.HexColor("#E7E9EE"), strokeWidth=0.6))
        drawing.add(String(left - 8, y - 2.5, f"{high * i / 4:,.0f}", textAnchor="end", fillColor=MUTED, fontName="Helvetica", fontSize=6.5))
    drawing.add(Line(left, baseline, width - right, baseline, strokeColor=LIGHT_GREY, strokeWidth=0.8))
    group_width = plot_width / len(categories)
    bar_width = min(38, group_width * 0.28)
    for i, category in enumerate(categories):
        center = left + group_width * (i + 0.5)
        for j, value in enumerate((previous[i], current[i])):
            value = max(_float(value, 0), 0)
            bar_height = plot_height * value / high
            x = center - bar_width if j == 0 else center
            fill = LIGHT_GREY if j == 0 else NAVY
            drawing.add(Rect(x, baseline, bar_width, bar_height, fillColor=fill, strokeColor=fill))
            drawing.add(String(x + bar_width / 2, baseline + bar_height + 5, f"{value:,.0f}", textAnchor="middle", fillColor=INK, fontName="Helvetica-Bold", fontSize=6.7))
        drawing.add(String(center, 13, category, textAnchor="middle", fillColor=MUTED, fontName="Helvetica", fontSize=7.2))
    drawing.add(Rect(59, height - 18, 7, 7, fillColor=LIGHT_GREY, strokeColor=LIGHT_GREY))
    drawing.add(String(70, height - 17, previous_label, fillColor=MUTED, fontName="Helvetica", fontSize=7.2))
    drawing.add(Rect(150, height - 18, 7, 7, fillColor=NAVY, strokeColor=NAVY))
    drawing.add(String(161, height - 17, current_label, fillColor=NAVY, fontName="Helvetica", fontSize=7.2))
    return drawing


def _latest_pair(df, value_col):
    if not isinstance(df, pd.DataFrame) or df.empty or value_col not in df.columns:
        return None, None, "Previous", "Latest"
    data = df.copy()
    data["date"] = pd.to_datetime(data.get("date"), errors="coerce")
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna(subset=["date", value_col]).sort_values("date").tail(2)
    if len(data) < 2:
        latest = _float(data[value_col].iloc[-1]) if len(data) else None
        return latest, latest, "Previous", "Latest"
    return (
        float(data[value_col].iloc[-2]),
        float(data[value_col].iloc[-1]),
        data["date"].iloc[-2].strftime("%b %Y"),
        data["date"].iloc[-1].strftime("%b %Y"),
    )


def _summary_cards(ctx):
    d_scfi = _float(ctx.get("d_scfi"), 0)
    d_housing = _float(ctx.get("d_housing"), 0)
    d_permits = _float(ctx.get("d_permits"), 0)
    d_fx = _float(ctx.get("d_fx"), 0)

    if d_scfi >= 5:
        freight_title = "Freight pressure is rebuilding"
        freight_text = f"SCFI increased {_change(d_scfi, '4W')}. Buyers should recheck booking windows and quote validity."
    elif d_scfi <= -5:
        freight_title = "Freight is easing from recent levels"
        freight_text = f"SCFI declined {_change(d_scfi, '4W')}. The direction is favorable, but route-level pricing may remain uneven."
    else:
        freight_title = "Freight is holding in a narrow range"
        freight_text = f"SCFI moved {_change(d_scfi, '4W')}. The market is steadier, with no strong directional break yet."

    if d_housing > 3 and d_permits > 0:
        demand_title = "Housing pipeline is improving"
        demand_text = f"Starts rose {_change(d_housing, 'MoM')} and permits also advanced, supporting a more constructive medium-term read."
    elif d_housing < -3 and d_permits < 0:
        demand_title = "Housing pipeline remains soft"
        demand_text = f"Starts changed {_change(d_housing, 'MoM')} while permits also weakened. Demand visibility remains selective."
    else:
        demand_title = "Housing signals remain mixed"
        demand_text = f"Starts changed {_change(d_housing, 'MoM')} and permits {_change(d_permits, 'MoM')}; the pipeline has not aligned in one direction."

    if d_fx >= 1.5:
        fx_title = "The won has weakened against the dollar"
        fx_text = f"USD/KRW increased {_change(d_fx, '20D')}, improving Korean export conversion but adding FX movement to customer discussions."
    elif d_fx <= -1.5:
        fx_title = "The won has firmed against the dollar"
        fx_text = f"USD/KRW declined {_change(d_fx, '20D')}, narrowing some export-price cushion while reducing recent volatility."
    else:
        fx_title = "FX has moved into a calmer band"
        fx_text = f"USD/KRW changed {_change(d_fx, '20D')}. Near-term currency noise is lower than in a directional move."

    return [
        ("01", freight_title, freight_text),
        ("02", demand_title, demand_text),
        ("03", fx_title, fx_text),
    ]


def _default_kcc_view(ctx):
    d_scfi = _float(ctx.get("d_scfi"), 0)
    d_fx = _float(ctx.get("d_fx"), 0)
    mortgage = _float(ctx.get("mortgage"))
    freight = "rising" if d_scfi >= 5 else "easing" if d_scfi <= -5 else "stable"
    fx = "volatile" if abs(d_fx) >= 2 else "contained"
    rate_text = "financing conditions remain restrictive" if mortgage is not None and mortgage >= 6 else "financing conditions are becoming less restrictive"
    return [
        (
            f"We read the current market as <b>selective rather than one-directional</b>: freight is {freight}, "
            f"FX movement is relatively {fx}, and {rate_text}. Public indicators support measured planning, "
            "but they do not yet point to a broad demand or landed-cost reset."
        ),
        (
            "For buyers, the more actionable variable is <b>timing and visibility</b>. Align inventory with confirmed "
            "projects, review booking windows against actual lane quotations, and keep quote-validity assumptions explicit. "
            "KCC Glass will continue to monitor the next freight, housing and FX releases and flag any material inflection."
        ),
    ]


def _market_read(ctx):
    d_fx = _change(ctx.get("d_fx"), "20D")
    d_scfi = _change(ctx.get("d_scfi"), "4W")
    d_housing = _change(ctx.get("d_housing"), "MoM")
    d_permits = _change(ctx.get("d_permits"), "MoM")
    mortgage = _fmt(ctx.get("mortgage"), "{:.2f}%")
    return [
        (
            f"<b>Currency and freight.</b> USD/KRW is {_fmt(ctx.get('usd_krw'), '{:,.0f}')} ({d_fx}), while SCFI is "
            f"{_fmt(ctx.get('scfi'), '{:,.0f}')} ({d_scfi}). Read these as quote-validity and booking-context signals; "
            "route-level freight and the actual conversion date still determine the commercial outcome."
        ),
        (
            f"<b>Demand backdrop.</b> Housing starts changed {d_housing}, permits changed {d_permits}, and the 30-year "
            f"mortgage rate is {mortgage}. The combination supports project- and account-specific planning rather than "
            "a single broad-market demand call."
        ),
    ]


def create_customer_market_signal_pdf(ctx, config, logo_path=None):
    """Build a four-page, customer-safe English market brief."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=13 * mm,
        bottomMargin=15 * mm,
        title="KCC Glass LVT Market Signal",
        author="KCC Glass PL/LVT Export Sales",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("SignalTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=24, leading=27, textColor=NAVY, alignment=TA_LEFT)
    eyebrow = ParagraphStyle("SignalEyebrow", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=10, textColor=KCC_RED, tracking=1.4)
    subtitle = ParagraphStyle("SignalSubtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=MUTED)
    body = ParagraphStyle("SignalBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.4, leading=12.1, textColor=INK)
    body_bold = ParagraphStyle("SignalBodyBold", parent=body, fontName="Helvetica-Bold", textColor=NAVY)
    small = ParagraphStyle("SignalSmall", parent=body, fontSize=6.8, leading=9.2, textColor=MUTED)
    micro = ParagraphStyle("SignalMicro", parent=small, fontSize=6.2, leading=8.2, textColor=colors.HexColor("#A0A5AE"))
    section = ParagraphStyle("SignalSection", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=NAVY, spaceBefore=2, spaceAfter=5)
    section_note = ParagraphStyle("SignalSectionNote", parent=small, fontName="Helvetica-Oblique", fontSize=7.2, leading=9.2, alignment=TA_RIGHT, textColor=MUTED)
    card_num = ParagraphStyle("CardNum", parent=small, fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=KCC_RED)
    card_title = ParagraphStyle("CardTitle", parent=body, fontName="Helvetica-Bold", fontSize=8.5, leading=10.5, textColor=NAVY)
    card_body = ParagraphStyle("CardBody", parent=body, fontSize=7.2, leading=10, textColor=colors.HexColor("#4D535E"))
    table_body = ParagraphStyle("TableBody", parent=body, fontSize=7.1, leading=9.7, textColor=INK)
    table_bold = ParagraphStyle("TableBold", parent=table_body, fontName="Helvetica-Bold")
    table_header = ParagraphStyle("TableHeader", parent=table_body, fontName="Helvetica-Bold", textColor=colors.white)
    kcc_body = ParagraphStyle("KccBody", parent=body, fontSize=8.2, leading=12, textColor=INK)
    white_body = ParagraphStyle("WhiteBody", parent=body, fontSize=8.1, leading=11.5, textColor=colors.white)
    white_k = ParagraphStyle("WhiteK", parent=small, fontName="Helvetica-Bold", fontSize=6.8, leading=8.4, textColor=GOLD, tracking=1.2)
    meta_right = ParagraphStyle("MetaRight", parent=small, fontSize=7.3, leading=9.5, alignment=TA_RIGHT, textColor=MUTED)

    report_month = config.get("report_month") or datetime.now().date()
    report_month = pd.Timestamp(report_month)
    issue = str(config.get("issue", "01")).zfill(2)
    region = config.get("region", "North America")
    prepared_by = config.get("prepared_by", "KCC Glass PL/LVT Export Sales Team")
    contact = config.get("contact", "")
    policy_note = str(config.get("policy_note", "")).strip()
    include_policy = bool(config.get("include_policy")) and bool(policy_note)
    asof = ctx.get("asof", {}) or {}
    data_asof = config.get("data_asof") or max([str(v) for v in asof.values() if v and v != "N/A"], default=report_month.strftime("%b %Y"))

    def section_head(number, name):
        badge = Paragraph(f"<b>{number}</b>", ParagraphStyle("Badge", parent=small, fontName="Helvetica-Bold", fontSize=7.3, leading=9, textColor=colors.white, alignment=1))
        table = Table([["", badge, Paragraph(name, section)]], colWidths=[1.5 * mm, 9 * mm, 166.5 * mm], rowHeights=[7.5 * mm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), NAVY),
            ("BACKGROUND", (1, 0), (1, 0), KCC_RED),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (0, 0), 2),
            ("RIGHTPADDING", (0, 0), (0, 0), 2),
            ("LEFTPADDING", (1, 0), (1, 0), 2),
            ("RIGHTPADDING", (1, 0), (1, 0), 2),
            ("LEFTPADDING", (2, 0), (2, 0), 5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.7, LINE),
        ]))
        return table

    def exhibit(number, title_text, chart, source_text):
        title_line = Paragraph(f'<font color="#E30613"><b>Exhibit {number}.</b></font> <b>{_escape(title_text)}</b>', body)
        source_line = Paragraph(f"Source: {_escape(source_text)}", micro)
        box = Table([[title_line], [chart], [source_line]], colWidths=[177 * mm])
        box.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.45, LINE),
            ("LINEABOVE", (0, 0), (-1, 0), 1.2, GOLD),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FCFCFD")),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ALIGN", (0, 2), (-1, 2), "RIGHT"),
        ]))
        return KeepTogether([box])

    def on_page(canvas, doc_obj):
        canvas.saveState()
        page = doc_obj.page
        if page > 1:
            canvas.setFont("Helvetica-Bold", 6.5)
            canvas.setFillColor(colors.HexColor("#B0B5C0"))
            canvas.drawString(14 * mm, A4[1] - 8.5 * mm, "LVT MARKET SIGNAL")
            canvas.drawRightString(A4[0] - 14 * mm, A4[1] - 8.5 * mm, "KCC GLASS | PL/LVT EXPORT SALES")
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.4)
        canvas.line(14 * mm, 11 * mm, A4[0] - 14 * mm, 11 * mm)
        canvas.setFont("Helvetica", 6.3)
        canvas.setFillColor(colors.HexColor("#A8ADB6"))
        canvas.drawString(14 * mm, 7 * mm, f"Issue #{issue} | {report_month.strftime('%B %Y')}")
        canvas.drawCentredString(A4[0] / 2, 7 * mm, "Market-awareness use only | Not a price quotation")
        canvas.setFont("Helvetica-Bold", 6.5)
        canvas.setFillColor(NAVY)
        canvas.drawRightString(A4[0] - 14 * mm, 7 * mm, f"{page} / 4")
        canvas.restoreState()

    module_dir = os.path.dirname(os.path.abspath(__file__))
    logo_candidates = [
        logo_path,
        os.path.join(module_dir, "kcc_glass_ci_full_color.png"),
        os.path.join(module_dir, "logo_navy_t.png"),
    ]
    logo_file = next(
        (candidate for candidate in logo_candidates if candidate and os.path.isfile(candidate)),
        None,
    )
    if logo_file:
        logo = Image(logo_file, width=39 * mm, height=10 * mm)
    else:
        logo = Paragraph("KCC GLASS", ParagraphStyle("FallbackLogo", parent=title, fontSize=16, leading=18))
    header = Table(
        [[logo, Paragraph(f"PL / LVT Export Sales<br/>Market Intelligence Series<br/>Issue #{issue} | {report_month.strftime('%B %Y')}", meta_right)]],
        colWidths=[90 * mm, 87 * mm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, -1), 1.7, NAVY),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    intro = Table([[Paragraph(
        "This brief supports partners' sourcing, inventory and pricing discussions. It uses public market indicators, states the data date clearly and separates market context from commercial commitments.",
        body,
    )]], colWidths=[177 * mm])
    intro.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE_BLUE),
        ("LINEBEFORE", (0, 0), (0, -1), 2.2, NAVY),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    cards = []
    for number, heading, text in _summary_cards(ctx):
        card = Table(
            [[Paragraph(number, card_num)], [Paragraph(_escape(heading), card_title)], [Paragraph(_escape(text), card_body)]],
            colWidths=[55 * mm],
        )
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), SOFT),
            ("BOX", (0, 0), (-1, -1), 0.35, LINE),
            ("LINEABOVE", (0, 0), (-1, 0), 1.5, NAVY),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, 0), 7),
            ("TOPPADDING", (0, 1), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -2), 2),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 8),
        ]))
        cards.append(card)
    card_table = Table([cards], colWidths=[59 * mm] * 3)
    card_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    summary_header = Table(
        [[Paragraph("Executive Summary", section), Paragraph("Three signals buyers should watch this month - a 30-second read", section_note)]],
        colWidths=[62 * mm, 115 * mm],
    )
    summary_header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    signal_rows = [
        ["Indicator", "Latest", "Change", "Data as of"],
        ["USD / KRW", _fmt(ctx.get("usd_krw"), "{:,.0f}"), _change(ctx.get("d_fx"), "20D"), asof.get("fx", "N/A")],
        ["SCFI", _fmt(ctx.get("scfi"), "{:,.0f}"), _change(ctx.get("d_scfi"), "4W"), asof.get("freight", "N/A")],
        ["CCFI", _fmt(ctx.get("ccfi"), "{:,.0f}"), _change(ctx.get("d_ccfi"), "4W"), asof.get("freight", "N/A")],
        ["U.S. Housing Starts", _fmt(ctx.get("housing"), "{:,.0f}K"), _change(ctx.get("d_housing"), "MoM"), asof.get("housing", "N/A")],
        ["Building Permits", _fmt(ctx.get("permits"), "{:,.0f}K"), _change(ctx.get("d_permits"), "MoM"), asof.get("housing", "N/A")],
        ["30Y Mortgage", _fmt(ctx.get("mortgage"), "{:.2f}%"), _change(ctx.get("d_mortgage"), "WoW", 2), asof.get("mortgage", "N/A")],
        ["WTI / Brent", f"{_fmt(ctx.get('wti'), '${:.1f}')} / {_fmt(ctx.get('brent'), '${:.1f}')}", f"{_change(ctx.get('d_wti'))} / {_change(ctx.get('d_brent'))}", asof.get("energy", "N/A")],
    ]
    signal_table = Table(signal_rows, colWidths=[49 * mm, 39 * mm, 43 * mm, 46 * mm], repeatRows=1)
    signal_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("FONTSIZE", (0, 0), (-1, 0), 7.2),
        ("FONTSIZE", (0, 1), (-1, -1), 7.0),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FB")]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
        ("ALIGN", (1, 1), (2, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    story = [
        header,
        Spacer(1, 7),
        Paragraph(f"{_escape(region.upper())} FLOORING TRADE BRIEF", eyebrow),
        Spacer(1, 2),
        Paragraph("LVT Market Signal", title),
        Paragraph(f"A monthly read on the macro, freight and demand signals shaping the {region} LVT trade.", subtitle),
        Paragraph(f"Prepared by {_escape(prepared_by)} &nbsp; | &nbsp; Data as of {_escape(data_asof)}", small),
        Spacer(1, 7),
        intro,
        Spacer(1, 8),
        summary_header,
        card_table,
        Spacer(1, 7),
        section_head("01", "Market Signals"),
        Spacer(1, 5),
        signal_table,
        Spacer(1, 7),
        section_head("02", "Market Read"),
        Spacer(1, 4),
        Paragraph(_market_read(ctx)[0], body),
        Spacer(1, 4),
        Paragraph(_market_read(ctx)[1], body),
        PageBreak(),
    ]

    fx_labels, fx_values = _series_points(ctx.get("fx_df"), "USD/KRW", periods=7, resample="ME")
    freight_labels, scfi_values = _series_points(ctx.get("freight_df"), "SCFI", periods=7, resample="ME")
    _, ccfi_values = _series_points(ctx.get("freight_df"), "CCFI", periods=7, resample="ME")
    story.extend([
        exhibit("1", "USD/KRW - seven-month trend", _line_chart(fx_labels, [("USD/KRW", fx_values)], palette=[NAVY]), f"FRED DEXKOUS; data through {asof.get('fx', 'N/A')}"),
        Spacer(1, 6),
        Paragraph(
            f"<b>Currency.</b> USD/KRW is {_fmt(ctx.get('usd_krw'), '{:,.0f}')}, a {_change(ctx.get('d_fx'), '20-trading-day')} move. For customer discussion, the most useful application is quote-validity and conversion context rather than a directional FX forecast.",
            body,
        ),
        Spacer(1, 7),
        exhibit("2", "SCFI and CCFI - recent trend", _line_chart(freight_labels, [("SCFI", scfi_values), ("CCFI", ccfi_values)], palette=[NAVY, GOLD]), f"National Logistics Information Center; data through {asof.get('freight', 'N/A')}"),
        Spacer(1, 6),
        Paragraph(
            f"<b>Freight.</b> SCFI is {_fmt(ctx.get('scfi'), '{:,.0f}')} ({_change(ctx.get('d_scfi'), '4W')}) and CCFI is {_fmt(ctx.get('ccfi'), '{:,.0f}')} ({_change(ctx.get('d_ccfi'), '4W')}). Route-level quotes may differ from index direction, so booking decisions should still be checked against the actual lane and shipment window.",
            body,
        ),
        PageBreak(),
    ])

    p_prev, p_now, prev_label, now_label = _latest_pair(ctx.get("permits_df"), "value")
    h_prev, h_now, _, _ = _latest_pair(ctx.get("housing_df"), "value")
    c_prev, c_now, _, _ = _latest_pair(ctx.get("complete_df"), "value")
    categories = ["Permits", "Starts", "Completions"]
    previous = [_float(p_prev, 0), _float(h_prev, 0), _float(c_prev, 0)]
    current = [_float(p_now, 0), _float(h_now, 0), _float(c_now, 0)]
    macro_rows = [
        ["Indicator", "Latest", "Change / context", "Use in customer discussion"],
        ["Existing Home Sales", _fmt(ctx.get("existing"), "{:.2f}M"), _change(ctx.get("d_existing"), "MoM"), "Replacement and remodeling demand context"],
        ["New Home Sales", _fmt(ctx.get("newsales"), "{:,.0f}K"), _change(ctx.get("d_newsales"), "MoM"), "New-build demand pulse"],
        ["30Y Mortgage", _fmt(ctx.get("mortgage"), "{:.2f}%"), _change(ctx.get("d_mortgage"), "WoW", 2), "Financing pressure and housing sentiment"],
        ["Fed Funds", _fmt(ctx.get("fedfunds"), "{:.2f}%"), "Policy rate", "Macro and financing backdrop"],
        ["CPI Index", _fmt(ctx.get("cpi"), "{:.1f}"), _change(ctx.get("d_cpi"), "MoM"), "Inflation environment"],
        ["WTI / Brent", f"{_fmt(ctx.get('wti'), '${:.1f}')} / {_fmt(ctx.get('brent'), '${:.1f}')}", f"{_change(ctx.get('d_wti'))} / {_change(ctx.get('d_brent'))}", "Energy and broader cost signal"],
    ]
    macro_table = Table(macro_rows, colWidths=[37 * mm, 32 * mm, 42 * mm, 66 * mm], repeatRows=1)
    macro_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6F7074")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 6.9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8F9FB")]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
        ("ALIGN", (1, 1), (2, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    why_it_matters = Table([[Paragraph("WHY IT MATTERS FOR LVT", white_k), Paragraph(
        "Permits, starts and completions describe different stages of the housing pipeline. Their direction helps frame medium-term flooring opportunity, while mortgage rates and home sales indicate how quickly that pipeline may translate into realized demand.",
        white_body,
    )]], colWidths=[42 * mm, 135 * mm])
    why_it_matters.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.extend([
        exhibit("3", "U.S. housing pipeline - previous vs. latest release", _grouped_bar_chart(categories, previous, current, prev_label, now_label), f"FRED / U.S. Census Bureau; data through {asof.get('housing', 'N/A')}"),
        Spacer(1, 6),
        why_it_matters,
        Spacer(1, 8),
        section_head("03", "Demand, Rates & Cost Watch"),
        Spacer(1, 5),
        macro_table,
    ])
    if include_policy:
        policy_box = Table([[Paragraph("VERIFIED POLICY WATCH", card_num), Paragraph(_escape(policy_note), body)]], colWidths=[42 * mm, 135 * mm])
        policy_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFF7E6")),
            ("LINEABOVE", (0, 0), (-1, -1), 1.2, GOLD),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.extend([Spacer(1, 7), policy_box])
    story.extend([
        Spacer(1, 8),
        section_head("04", "Implications for LVT Sourcing"),
        Spacer(1, 4),
        Paragraph("Translating this month's public signals into practical buyer discussion points:", body),
        PageBreak(),
    ])

    d_scfi = _float(ctx.get("d_scfi"), 0)
    d_fx = _float(ctx.get("d_fx"), 0)
    mortgage = _float(ctx.get("mortgage"), 0)
    d_housing = _float(ctx.get("d_housing"), 0)
    d_permits = _float(ctx.get("d_permits"), 0)

    if d_scfi >= 8:
        inventory_status = ("ELEVATED", PALE_RED, KCC_RED)
        inventory_note = "Freight momentum is elevated. <b>Protect critical lead times</b>, but keep inventory tied to confirmed programs rather than broad defensive over-ordering."
    elif d_scfi <= -5:
        inventory_status = ("EASING", PALE_BLUE, NAVY)
        inventory_note = "Freight is easing from recent levels, reducing the case for precautionary stock. <b>Use measured replenishment</b> while route-level pricing normalizes."
    else:
        inventory_status = ("MEASURED", PALE_BLUE, NAVY)
        inventory_note = "Current public signals support <b>measured inventory</b> aligned with confirmed project demand; they do not justify broad defensive over-ordering."

    if d_scfi >= 3:
        booking_status = ("ACT EARLY", PALE_GOLD, colors.HexColor("#8B6F1E"))
        booking_note = "Index momentum favors confirming capacity around known shipment windows. <b>Check actual lane quotations early</b>; an index is directional context, not a booking price."
    elif d_scfi <= -5:
        booking_status = ("FLEXIBLE", PALE_BLUE, NAVY)
        booking_note = "Cooling index momentum may improve optionality. <b>Keep booking windows flexible</b>, while verifying whether the relevant lane has followed the benchmark."
    else:
        booking_status = ("MONITOR", PALE_GREY, colors.HexColor("#666A72"))
        booking_note = "Freight is not showing a decisive break. <b>Monitor capacity and surcharges</b> around the actual shipment window before changing booking cadence."

    if abs(d_fx) >= 2 or abs(d_scfi) >= 8:
        price_status = ("VOLATILE", PALE_RED, KCC_RED)
        price_note = "Currency or freight movement remains material. <b>Shorten quote-validity assumptions</b> and review FX, freight and energy together before discussing landed-cost direction."
    elif abs(d_fx) < 1 and abs(d_scfi) < 3:
        price_status = ("STEADIER", PALE_BLUE, NAVY)
        price_note = "FX and freight are comparatively contained. <b>Visibility has improved</b>, although route quotes and the actual conversion date still determine the commercial outcome."
    else:
        price_status = ("MIXED", PALE_GREY, colors.HexColor("#666A72"))
        price_note = "The cost signals are not aligned in one direction. <b>Avoid a single-factor price conclusion</b>; review FX, freight and energy as one landed-cost bridge."

    if d_housing > 3 and d_permits >= 0:
        demand_status = ("IMPROVING", PALE_BLUE, NAVY)
        demand_note = "The housing pipeline is becoming more constructive, but financing remains a constraint. <b>Prioritize visible projects and active accounts</b> over a broad-market volume assumption."
    elif d_housing < -3 and d_permits < 0:
        demand_status = ("SOFT", PALE_RED, KCC_RED)
        demand_note = "Starts and permits are both soft. <b>Plan around confirmed programs and replacement demand</b> rather than assuming a near-term new-build recovery."
    else:
        demand_status = ("SELECTIVE", PALE_GREY, colors.HexColor("#666A72"))
        demand_note = f"Housing signals remain mixed and the mortgage rate is {_fmt(mortgage, '{:.2f}%')}. <b>Use account- and project-specific demand planning</b> rather than one broad market call."

    implication_items = [
        ("Inventory risk", inventory_status, inventory_note),
        ("Ocean booking timing", booking_status, booking_note),
        ("Price visibility", price_status, price_note),
        ("Demand focus", demand_status, demand_note),
    ]
    implication_rows = [[Paragraph(cell, table_header) for cell in ["Lever", "Direction", "What it may mean for buyers"]]]
    for lever, status, note in implication_items:
        label, fill_color, text_color = status
        implication_rows.append([
            Paragraph(_escape(lever), table_bold),
            _StatusBadge(label, fill_color, text_color),
            Paragraph(note, table_body),
        ])
    implication_table = Table(implication_rows, colWidths=[41 * mm, 39 * mm, 97 * mm], repeatRows=1)
    implication_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 1), (2, -1), "Helvetica"),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("TEXTCOLOR", (0, 1), (-1, -1), INK),
        ("FONTSIZE", (0, 0), (-1, -1), 7.3),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F7F9")]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("VALIGN", (1, 1), (1, -1), "MIDDLE"),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    kcc_view_override = str(config.get("kcc_view") or "").strip()
    if kcc_view_override:
        view_texts = [_escape(part.strip()) for part in kcc_view_override.split("\n\n") if part.strip()]
    else:
        view_texts = _default_kcc_view(ctx)
    kcc_view_flowables = []
    for index, view_text in enumerate(view_texts):
        if index:
            kcc_view_flowables.append(Spacer(1, 5))
        kcc_view_flowables.append(Paragraph(view_text, kcc_body))
    kcc_box = Table([
        [Paragraph("KCC", ParagraphStyle("KccTag", parent=small, fontName="Helvetica-Bold", fontSize=7, leading=8, textColor=colors.white, alignment=1)), Paragraph("View", ParagraphStyle("KccViewTitle", parent=section, textColor=colors.white, fontSize=11, leading=13))],
        [kcc_view_flowables, ""],
    ], colWidths=[14 * mm, 163 * mm])
    kcc_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), KCC_RED),
        ("BACKGROUND", (1, 0), (1, 0), NAVY),
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8F9FC")),
        ("TEXTCOLOR", (0, 1), (-1, 1), INK),
        ("SPAN", (0, 1), (1, 1)),
        ("BOX", (0, 0), (-1, -1), 0.8, NAVY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    source_lines = [
        f"FRED / U.S. Census housing and macro releases: {asof.get('housing', 'N/A')}",
        f"FRED DEXKOUS and live FX reference: {asof.get('fx', 'N/A')}",
        f"National Logistics Information Center SCFI/CCFI: {asof.get('freight', 'N/A')}",
        f"FRED WTI and Brent crude references: {asof.get('energy', 'N/A')}",
    ]
    source_table = Table([[Paragraph("SOURCE NOTES", card_num), Paragraph("<br/>".join(_escape(x) for x in source_lines), small)]], colWidths=[37 * mm, 140 * mm])
    source_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SOFT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    monitor_items = [
        ("FREIGHT", "Watch whether SCFI and CCFI confirm the same direction and compare the index with actual lane quotations."),
        ("HOUSING", "Track permits, starts and mortgage rates together to separate pipeline improvement from realized demand."),
        ("FX & ENERGY", "Review the USD/KRW range and WTI/Brent direction before the next customer pricing discussion."),
    ]
    monitor_cells = []
    for label, note in monitor_items:
        monitor_cells.append([Paragraph(label, card_num), Paragraph(note, card_body)])
    monitor_table = Table([monitor_cells], colWidths=[57.7 * mm] * 3)
    monitor_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.4, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, LINE),
        ("LINEABOVE", (0, 0), (-1, -1), 1.2, GOLD),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    contact_line = f" For questions, please contact {_escape(contact)}." if contact else ""
    disclaimer = Paragraph(
        "This brief is shared for market-awareness purposes only and does not constitute a price quotation, contract term, market forecast, legal advice or investment advice. Figures are drawn from public sources, may be revised, and should be checked against the latest official release before use." + contact_line + " (c) KCC Glass Corporation.",
        micro,
    )
    story.extend([
        implication_table,
        Spacer(1, 9),
        kcc_box,
        Spacer(1, 9),
        Paragraph("Next Issue Monitor", section),
        monitor_table,
        Spacer(1, 9),
        source_table,
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=0.5, color=LINE),
        Spacer(1, 5),
        disclaimer,
    ])

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    buffer.seek(0)
    return buffer
