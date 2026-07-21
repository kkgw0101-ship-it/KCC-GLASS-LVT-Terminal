"""Customer-facing integrated KCC Glass LVT market and design brief."""

from __future__ import annotations

import os
from datetime import date
from io import BytesIO

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from customer_brief import _change, _fmt, _line_chart, _series_points
from design_brief import (
    GOLD,
    INK,
    KCC_RED,
    LINE,
    MUTED,
    NAVY,
    PALE_BLUE,
    PALE_GOLD,
    SOFT,
    WHITE,
    _bar_chart,
    _callout,
    _date_label,
    _escape,
    _fit_image,
    _frame,
    _section_head,
    _short,
    _signal_cards,
    _styles,
    _table,
    _taxonomy_top,
)


def _market_value_rows(ctx):
    asof = dict(ctx.get("asof") or {})
    return [
        ["USD / KRW", _fmt(ctx.get("usd_krw"), "{:,.0f}"), _change(ctx.get("d_fx"), "20D"), asof.get("fx", "N/A")],
        ["SCFI", _fmt(ctx.get("scfi"), "{:,.0f}"), _change(ctx.get("d_scfi"), "4W"), asof.get("freight", "N/A")],
        ["CCFI", _fmt(ctx.get("ccfi"), "{:,.0f}"), _change(ctx.get("d_ccfi"), "4W"), asof.get("freight", "N/A")],
        ["U.S. Housing Starts", _fmt(ctx.get("housing"), "{:,.0f}K"), _change(ctx.get("d_housing"), "MoM"), asof.get("housing", "N/A")],
        ["Building Permits", _fmt(ctx.get("permits"), "{:,.0f}K"), _change(ctx.get("d_permits"), "MoM"), asof.get("housing", "N/A")],
        ["30Y Mortgage", _fmt(ctx.get("mortgage"), "{:.2f}%"), _change(ctx.get("d_mortgage"), "WoW", 2), asof.get("mortgage", "N/A")],
        ["WTI / Brent", f"{_fmt(ctx.get('wti'), '${:,.1f}')} / {_fmt(ctx.get('brent'), '${:,.1f}')}", f"{_change(ctx.get('d_wti'))} / {_change(ctx.get('d_brent'))}", asof.get("energy", "N/A")],
    ]


def _market_headline(ctx):
    freight = float(ctx.get("d_scfi") or 0)
    housing = float(ctx.get("d_housing") or 0)
    fx = float(ctx.get("d_fx") or 0)
    if freight >= 8:
        return "Freight pressure is rebuilding", "Recheck booking windows and quote validity before the next customer commitment."
    if housing <= -5:
        return "Demand signals remain cautious", "Use channel-specific sell-through evidence before extending inventory assumptions."
    if abs(fx) >= 2:
        return "Currency volatility needs attention", "Align quote validity and currency assumptions in each customer discussion."
    return "Market signals are mixed", "Use the indicators as a discussion framework rather than a directional demand forecast."


def _design_snapshot(design_ctx):
    keyword_df = _frame(design_ctx.get("keywords"), ["Keyword", "Mentions"])
    taxonomy_df = _frame(design_ctx.get("taxonomy"), ["Axis", "Trend Bucket", "Signal"])
    if not keyword_df.empty:
        keyword_df["Mentions"] = pd.to_numeric(keyword_df["Mentions"], errors="coerce").fillna(0)
        keyword_df = keyword_df.sort_values("Mentions", ascending=False)
    top_keyword = str(keyword_df.iloc[0]["Keyword"]) if not keyword_df.empty else "Design performance"
    material_rows = _taxonomy_top(taxonomy_df, "Material")
    color_rows = _taxonomy_top(taxonomy_df, "Color")
    pattern_rows = _taxonomy_top(taxonomy_df, "Pattern")
    material = str(material_rows[0][0]) if material_rows else "Wood"
    pattern = str(pattern_rows[0][0]) if pattern_rows else "Realistic Texture"
    return keyword_df, taxonomy_df, top_keyword, material, pattern, material_rows, color_rows, pattern_rows


def _page_chrome(logo_path, prepared_by):
    def draw(canvas, document):
        canvas.saveState()
        if logo_path and os.path.isfile(logo_path):
            canvas.drawImage(
                logo_path, 17 * mm, 281.5 * mm, width=31 * mm, height=8.5 * mm,
                preserveAspectRatio=True, anchor="sw", mask="auto",
            )
        else:
            canvas.setFillColor(NAVY)
            canvas.setFont("Helvetica-Bold", 13)
            canvas.drawString(17 * mm, 284 * mm, "KCC GLASS")
        canvas.setStrokeColor(NAVY)
        canvas.setLineWidth(0.8)
        canvas.line(17 * mm, 279 * mm, 193 * mm, 279 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.4)
        canvas.drawString(17 * mm, 10 * mm, "KCC Glass Market Intelligence | Customer discussion material")
        canvas.drawRightString(193 * mm, 10 * mm, str(document.page))
        canvas.restoreState()
    return draw


def create_customer_integrated_signal_pdf(market_ctx, design_ctx, config, logo_path=None, hero_path=None):
    """Create a five-page externally shareable market and design brief."""
    buffer = BytesIO()
    styles = _styles()
    issue = str(config.get("issue") or "01").zfill(2)
    report_date = config.get("report_date") or date.today()
    region = str(config.get("region") or "North America")
    prepared_by = str(config.get("prepared_by") or "KCC Glass PL/LVT Export Sales Team")
    contact = str(config.get("contact") or "")
    market_view = str(config.get("market_view") or "").strip()
    design_view = str(config.get("design_view") or "").strip()
    library_url = str(config.get("design_library_url") or "https://www.homecc.com/lvt/designlibrary.do")
    market_asof = str(config.get("market_asof") or "N/A")
    design_meta = dict(design_ctx.get("meta") or {})
    design_asof = str(config.get("design_asof") or design_meta.get("published_end") or "N/A")
    items = list(design_ctx.get("items") or [])
    keyword_df, taxonomy_df, top_keyword, material, pattern, material_rows, color_rows, pattern_rows = _design_snapshot(design_ctx)
    headline, headline_detail = _market_headline(market_ctx)

    if not market_view:
        market_view = (
            f"Current public indicators suggest that {headline.lower()}. Buyers should use freight, currency and housing signals "
            "to frame sourcing and inventory discussions while keeping commercial commitments customer-specific."
        )
    if not design_view:
        design_view = (
            f"Recent trade coverage gives {top_keyword.lower()} the highest visibility in the sampled design conversation, "
            f"with {material.lower()} references and {pattern.lower()} treatments providing practical starting points for assortment review."
        )

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=17 * mm,
        rightMargin=17 * mm,
        topMargin=25 * mm,
        bottomMargin=17 * mm,
        title="KCC Glass LVT Market and Design Signal",
        author=prepared_by,
        subject="Customer-facing LVT market and design intelligence brief",
    )
    story = []

    # Page 1: Executive snapshot
    story.extend([
        Table(
            [[Paragraph("", styles["body"]), Paragraph(
                f"PL / LVT Export Sales<br/>Market &amp; Design Intelligence<br/>Issue #{_escape(issue)} | {_escape(_date_label(report_date))}",
                styles["right"],
            )]],
            colWidths=[112 * mm, 64 * mm],
        ),
        Spacer(1, 3 * mm),
        Paragraph(f"{_escape(region.upper())} FLOORING TRADE BRIEF", styles["eyebrow"]),
        Paragraph("LVT Market &amp; Design Signal", styles["title"]),
        Paragraph("A concise, customer-ready read connecting market conditions with current flooring design conversations.", styles["subtitle"]),
        Paragraph(
            f"Prepared by {_escape(prepared_by)} &nbsp; | &nbsp; Market data as of {_escape(market_asof)} &nbsp; | &nbsp; Design coverage as of {_escape(design_asof)}",
            styles["small"],
        ),
        Spacer(1, 3 * mm),
        _callout(
            "This brief supports sourcing, inventory and assortment discussions. Public market indicators and sampled trade-design signals are kept separate from commercial commitments, pricing and customer-specific forecasts.",
            styles,
        ),
        Spacer(1, 5 * mm),
        Paragraph("Executive Snapshot", styles["h2"]),
        _signal_cards([
            (headline, headline_detail),
            (top_keyword.title(), "The most visible classified design keyword in the current article sample."),
            (f"{material} / {pattern}", "Material and surface cues to carry into a focused assortment discussion."),
        ], styles),
        Spacer(1, 6 * mm),
        Paragraph("Market Signal Board", styles["h2"]),
        _table(
            [["Indicator", "Latest", "Change", "Data as of"]] + [[_escape(v) for v in row] for row in _market_value_rows(market_ctx)[:6]],
            [45 * mm, 38 * mm, 44 * mm, 49 * mm], styles, font_size=6.9,
        ),
        Spacer(1, 4 * mm),
        Paragraph(
            "Reading principle: use the direction and date of each signal as context. Figures are not a price offer, demand forecast or inventory recommendation.",
            styles["small"],
        ),
        PageBreak(),
    ])

    # Page 2: Demand and macro
    housing_labels, housing_values = _series_points(market_ctx.get("housing_df"), "value", periods=18, resample="MS")
    permit_labels, permit_values = _series_points(market_ctx.get("permits_df"), "value", periods=18, resample="MS")
    complete_labels, complete_values = _series_points(market_ctx.get("complete_df"), "value", periods=18, resample="MS")
    labels = housing_labels or permit_labels or complete_labels
    story.extend([
        _section_head("01", "Demand and Macro Context", styles),
        Spacer(1, 4 * mm),
        _callout(
            "Housing starts, permits and completions describe different stages of the construction pipeline. Read them together with mortgage rates before drawing a channel-level demand conclusion.",
            styles,
        ),
        Spacer(1, 5 * mm),
        Paragraph("U.S. Housing Pipeline", styles["h2"]),
        _line_chart(
            labels,
            [("Starts", housing_values), ("Permits", permit_values), ("Completions", complete_values)],
            height=180,
        ),
        Spacer(1, 3 * mm),
        _table([
            ["Indicator", "Latest", "Change", "Commercial reading"],
            ["Housing Starts", _fmt(market_ctx.get("housing"), "{:,.0f}K"), _change(market_ctx.get("d_housing"), "MoM"), "Current ground-breaking activity; useful for near-term pipeline context."],
            ["Building Permits", _fmt(market_ctx.get("permits"), "{:,.0f}K"), _change(market_ctx.get("d_permits"), "MoM"), "Forward pipeline signal; compare with starts for conversion strength."],
            ["Completions", _fmt(market_ctx.get("complete"), "{:,.0f}K"), _change(market_ctx.get("d_complete"), "MoM"), "Projects reaching delivery; relevant to installation and replenishment timing."],
            ["30Y Mortgage", _fmt(market_ctx.get("mortgage"), "{:.2f}%"), _change(market_ctx.get("d_mortgage"), "WoW", 2), "Affordability and buyer-sentiment context; not a direct flooring demand measure."],
            ["CPI / Fed Funds", f"{_fmt(market_ctx.get('cpi'), '{:,.1f}')} / {_fmt(market_ctx.get('fedfunds'), '{:.2f}%')}", "Current levels", "Macro cost and financing backdrop for customer planning."],
        ], [35 * mm, 31 * mm, 34 * mm, 76 * mm], styles, font_size=6.65),
        Spacer(1, 5 * mm),
        Paragraph("Customer Discussion Implication", styles["h2"]),
        _callout(
            "Translate the pipeline into channel questions: Which regions are converting permits into starts? Where is dealer sell-through stronger than the national headline? Which projects need samples or availability confirmation now?",
            styles, color=PALE_GOLD,
        ),
        PageBreak(),
    ])

    # Page 3: Freight, FX and sourcing
    freight_df = market_ctx.get("freight_df")
    freight_labels, scfi_values = _series_points(freight_df, "SCFI", periods=18)
    _, ccfi_values = _series_points(freight_df, "CCFI", periods=18)
    fx_labels, fx_values = _series_points(market_ctx.get("fx_df"), "USD/KRW", periods=18, resample="MS")
    story.extend([
        _section_head("02", "Freight, FX and Sourcing Context", styles),
        Spacer(1, 4 * mm),
        _callout(
            "Freight indices and exchange rates affect landed-cost conversations on different time scales. Use the latest value together with recent direction and the stated source date.",
            styles,
        ),
        Spacer(1, 4 * mm),
        Paragraph("Container Freight Indices", styles["h2"]),
        _line_chart(freight_labels, [("SCFI", scfi_values), ("CCFI", ccfi_values)], height=145, palette=[NAVY, GOLD]),
        Spacer(1, 2 * mm),
        Paragraph("USD / KRW Trend", styles["h2"]),
        _line_chart(fx_labels, [("USD/KRW", fx_values)], height=125, palette=[GOLD]),
        Spacer(1, 3 * mm),
        _table([
            ["Planning area", "Current public signal", "Customer-facing action"],
            ["Booking window", f"SCFI {_fmt(market_ctx.get('scfi'), '{:,.0f}')} ({_change(market_ctx.get('d_scfi'), '4W')})", "Confirm sailing availability and avoid assuming one index applies to every lane."],
            ["Quote validity", f"USD/KRW {_fmt(market_ctx.get('usd_krw'), '{:,.0f}')} ({_change(market_ctx.get('d_fx'), '20D')})", "State the quote date, currency basis and validity period clearly."],
            ["Energy context", f"WTI / Brent {_fmt(market_ctx.get('wti'), '${:,.1f}')} / {_fmt(market_ctx.get('brent'), '${:,.1f}')}", "Use as broad cost context only; do not present it as a direct product-price formula."],
        ], [34 * mm, 52 * mm, 90 * mm], styles, font_size=6.7),
        Spacer(1, 5 * mm),
        Paragraph("Sourcing Decision Lens", styles["h2"]),
        _signal_cards([
            ("Booking", "Confirm lane-specific space, transit assumptions and the next practical booking window."),
            ("Currency", "Document the FX reference date and keep quote validity aligned with current volatility."),
            ("Energy", "Use oil benchmarks as background context while keeping product pricing evidence separate."),
        ], styles),
        PageBreak(),
    ])

    # Page 4: Design and assortment
    story.extend([
        _section_head("03", "Design and Assortment Signal", styles),
        Spacer(1, 4 * mm),
    ])
    hero = _fit_image(hero_path, 176 * mm, 48 * mm)
    if hero:
        story.extend([hero, Spacer(1, 3 * mm)])
    story.extend([
        _signal_cards([
            (top_keyword.title(), "Most visible classified keyword in the sampled public trade coverage."),
            (material, "Leading material reference for an initial visual-direction conversation."),
            (pattern, "Leading pattern or surface-treatment signal in the current sample."),
        ], styles),
        Spacer(1, 4 * mm),
        Paragraph("Keyword Visibility", styles["h2"]),
        _bar_chart(list(keyword_df.head(7)[["Keyword", "Mentions"]].itertuples(index=False, name=None)), height=125, color=GOLD),
        Spacer(1, 3 * mm),
        _table([
            ["Design axis", "Leading references", "How to use it"],
            ["Material", ", ".join(f"{name} ({int(score)})" for name, score in material_rows) or "N/A", "Select a small material family for customer review."],
            ["Color", ", ".join(f"{name} ({int(score)})" for name, score in color_rows) or "N/A", "Translate coverage into channel-appropriate palette options."],
            ["Pattern", ", ".join(f"{name} ({int(score)})" for name, score in pattern_rows) or "N/A", "Pair surface realism and format with the installation context."],
        ], [29 * mm, 73 * mm, 74 * mm], styles, font_size=6.7),
        Spacer(1, 3 * mm),
        Paragraph(
            "Source discipline: trend counts use recent FCW and Floor Covering News titles and summaries. Third-party article images and full text are not reproduced. The KCC visual above is an official company design-library reference.",
            styles["small"],
        ),
        PageBreak(),
    ])

    # Page 5: Integrated customer action guide
    evidence_rows = [["Date", "Source", "Selected public evidence"]]
    for item in items[:5]:
        title = _escape(_short(item.get("title"), 96))
        link = _escape(item.get("link", ""))
        evidence = Paragraph(f'<a href="{link}" color="#172D7C"><u>{title}</u></a>', styles["body"]) if link else title
        evidence_rows.append([
            _escape(item.get("published") or "Latest"),
            _escape(item.get("source_group") or item.get("source") or "Source"),
            evidence,
        ])
    story.extend([
        _section_head("04", "Integrated Customer Action Guide", styles),
        Spacer(1, 4 * mm),
        _table([
            ["Customer context", "Market question", "Design / assortment next step"],
            ["Distributor", "Which regions and inventory windows are most exposed to freight or FX movement?", "Shortlist two visual families and confirm replenishment-ready specifications."],
            ["Retail", "Which housing and financing signals best match local sell-through evidence?", "Translate the leading cues into a concise good-better-best display story."],
            ["Project / Builder", "Which starts, completions and delivery dates matter to the active pipeline?", "Confirm visuals, format, performance and sampling timing against project needs."],
        ], [33 * mm, 70 * mm, 73 * mm], styles, font_size=6.6),
        Spacer(1, 5 * mm),
        Paragraph("KCC Market View", styles["h2"]),
        _callout(market_view, styles),
        Spacer(1, 4 * mm),
        Paragraph("KCC Design View", styles["h2"]),
        _callout(design_view, styles, color=PALE_GOLD),
        Spacer(1, 4 * mm),
        Paragraph("Selected Public Design Evidence", styles["h2"]),
        _table(evidence_rows, [27 * mm, 25 * mm, 124 * mm], styles, font_size=6.45),
        Spacer(1, 4 * mm),
        Table(
            [[
                Paragraph("Review selectable KCC patterns and prepare a focused customer sample discussion.", styles["body"]),
                Paragraph(f'<a href="{_escape(library_url)}" color="#172D7C"><u>Open KCC LVT Design Library</u></a>', styles["h3"]),
            ]],
            colWidths=[116 * mm, 60 * mm],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
            ]),
        ),
        Spacer(1, 4 * mm),
        HRFlowable(width="100%", thickness=0.7, color=LINE),
        Spacer(1, 2 * mm),
        Paragraph(
            "Methodology and disclaimer. Market figures are public indicators with panel-level source dates. Design signals are rule-based counts from a bounded sample of recent trade-article titles and summaries. This material is for discussion only and is not a forecast, price offer, product commitment or legal/policy advice. "
            + (f"Contact: {_escape(contact)}" if contact else "Please contact your KCC Glass representative for current availability and specifications."),
            styles["tiny"],
        ),
    ])

    chrome = _page_chrome(logo_path, prepared_by)
    doc.build(story, onFirstPage=chrome, onLaterPages=chrome)
    buffer.seek(0)
    return buffer
