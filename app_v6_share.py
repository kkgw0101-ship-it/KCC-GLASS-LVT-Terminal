"""
KCC Glass — LVT Intelligence Terminal (app_v6)
Bloomberg-style dashboard + 수익성 시뮬레이터
- 다크/라이트 토글
- FRED 실시간 지표 + 항구별 랜딩코스트 + LLM 분석 + 수익성 시뮬레이터
"""

import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime
import os
import base64
import html

# .env 파일에서 API 키 자동 로드 (있으면 — 매번 set 안 해도 됨)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import llm_analysis as llm

st.set_page_config(
    page_title="KCC Glass | LVT Terminal",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── API 키 ────────────────────────────────────────────────────
def get_secret(name, default=""):
    try:
        return st.secrets.get(name, os.environ.get(name, default))
    except Exception:
        return os.environ.get(name, default)

api_key = get_secret("FRED_API_KEY", "여기에_본인_API_KEY_입력")
anthropic_key = get_secret("ANTHROPIC_API_KEY", "")

# ── 로고 로드 ─────────────────────────────────────────────────
def _logo(path):
    try:
        with open(os.path.join(os.path.dirname(__file__), path), "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""
LOGO_WHITE = _logo("logo_white_t.png")  # 다크 헤더용 (항상 사용 - 헤더가 네이비)
LOGO_NAVY  = _logo("logo_navy_t.png")   # 라이트 모드 대비용

# ── 테마 상태 ─────────────────────────────────────────────────
if "theme" not in st.session_state:
    st.session_state.theme = "dark"

# ════════════════════════════════════════════════════════════
# CSS — Bloomberg Terminal Style (다크/라이트 CSS 변수)
# ════════════════════════════════════════════════════════════
THEME_VARS = {
    "dark": {
        "bg": "#0A0E14", "panel": "#11161F", "panel2": "#161C28",
        "border": "#1F2733", "grid": "#1A212C", "text": "#E4E9F0",
        "text2": "#8A95A5", "text3": "#5A6573", "accent": "#2D7FF9",
        "up": "#15B86B", "down": "#F0454A", "chart_grid": "#1A212C",
    },
    "light": {
        "bg": "#F4F6FA", "panel": "#FFFFFF", "panel2": "#FAFBFD",
        "border": "#E2E7EF", "grid": "#EDF1F6", "text": "#0F1722",
        "text2": "#5A6677", "text3": "#98A2B3", "accent": "#0E2372",
        "up": "#0E9F5C", "down": "#E0353A", "chart_grid": "#EDF1F6",
    },
}
T = THEME_VARS[st.session_state.theme]
NAVY = "#0E2372"
GOLD = "#E8B339"

st.markdown(f"""
<style>
[data-testid="stAppViewContainer"] {{ background:{T['bg']}; color:{T['text']}; }}
[data-testid="stHeader"] {{ background:transparent; height:0; }}
#MainMenu, footer, [data-testid="stToolbar"] {{ visibility:hidden; }}

/* ── 사이드바 항상 펼침 고정 (접기 버튼 숨김) ── */
[data-testid="stSidebarCollapseButton"] {{ display: none !important; }}
[data-testid="stSidebarCollapsedControl"] {{ display: none !important; }}
[data-testid="stSidebar"] {{ transform: none !important; visibility: visible !important; min-width: 230px !important; }}
[data-testid="stSidebar"][aria-expanded="false"] {{ margin-left: 0 !important; }}

.block-container {{ padding:0.5rem 1.2rem 2rem 1.2rem; max-width:100%; }}
* {{ font-variant-numeric: tabular-nums; }}

/* 사이드바 */
[data-testid="stSidebar"] {{ background:{NAVY}; border-right:1px solid {T['border']}; width:230px !important; }}
[data-testid="stSidebar"] * {{ color:#FFFFFF !important; }}
.sb-brand {{ font-size:13px; font-weight:800; letter-spacing:1.5px; color:#fff !important; padding:6px 0 2px 0; }}
.sb-sub {{ font-size:10px; color:#9FB0D9 !important; padding-bottom:14px; border-bottom:1px solid #1E3A8A; margin-bottom:12px; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{ padding:7px 10px; border-radius:7px; margin:1px 0; font-size:13px; transition:background 0.15s; }}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background:rgba(255,255,255,0.08); }}

/* 모노 폰트 숫자 */
.mono {{ font-family:'SF Mono','Roboto Mono','Consolas',monospace; font-variant-numeric:tabular-nums; }}

/* 상단 티커바 */
.topbar {{ background:{NAVY}; border-bottom:2px solid {GOLD}; border-radius:8px;
  padding:10px 18px; margin-bottom:14px; display:flex; align-items:center; justify-content:space-between; }}
.topbar-logo {{ height:24px; }}
.ticker {{ display:flex; gap:22px; align-items:center; }}
.tk {{ display:flex; flex-direction:column; align-items:flex-end; line-height:1.25; }}
.tk-l {{ font-size:9px; color:rgba(255,255,255,0.55); letter-spacing:0.5px; text-transform:uppercase; }}
.tk-v {{ font-size:13px; font-weight:700; color:#fff; font-family:'SF Mono','Consolas',monospace; }}
.tk-up {{ color:#4ADE80; }} .tk-dn {{ color:#FF6B6E; }}

/* 섹션 헤더 */
.sec {{ display:flex; align-items:baseline; gap:10px; margin:2px 0 12px 0; }}
.sec-t {{ font-size:16px; font-weight:700; letter-spacing:-0.2px; color:{T['text']}; }}
.sec-s {{ font-size:11px; color:{T['text3']}; }}
.live {{ display:inline-flex; align-items:center; gap:5px; font-size:10px; color:{T['up']};
  background:color-mix(in srgb, {T['up']} 13%, transparent); padding:2px 8px; border-radius:4px; font-weight:700; text-transform:uppercase; }}
.dot {{ width:6px; height:6px; border-radius:50%; background:{T['up']}; animation:bl 1.6s infinite; }}
@keyframes bl {{ 0%,100%{{opacity:1}} 50%{{opacity:0.3}} }}

/* KPI strip */
.kpi-strip {{ display:grid; grid-template-columns:repeat(6,1fr); gap:1px; background:{T['border']};
  border:1px solid {T['border']}; border-radius:8px; overflow:hidden; margin-bottom:14px; }}
.kpi {{ background:{T['panel']}; padding:11px 14px; }}
.kpi-n {{ font-size:10px; color:{T['text2']}; letter-spacing:0.5px; text-transform:uppercase; font-weight:600; margin-bottom:5px; }}
.kpi-v {{ font-size:21px; font-weight:700; letter-spacing:-0.5px; line-height:1; color:{T['text']}; font-family:'SF Mono','Consolas',monospace; }}
.kpi-c {{ font-size:11px; font-weight:600; margin-top:5px; }}
.up {{ color:{T['up']}; }} .dn {{ color:{T['down']}; }} .fl {{ color:{T['text3']}; }}

/* 패널 */
.panel {{ background:{T['panel']}; border:1px solid {T['border']}; border-radius:8px; overflow:hidden; margin-bottom:12px; }}
.p-head {{ padding:10px 14px; border-bottom:1px solid {T['border']}; display:flex; justify-content:space-between; align-items:center; }}
.p-t {{ font-size:12px; font-weight:700; letter-spacing:0.2px; color:{T['text']}; }}
.p-m {{ font-size:10px; color:{T['text3']}; font-family:'SF Mono','Consolas',monospace; }}
.p-body {{ padding:14px; }}

/* 데이터 테이블 */
.dt {{ width:100%; border-collapse:collapse; font-size:12px; }}
.dt th {{ text-align:right; padding:7px 10px; font-size:10px; color:{T['text3']}; text-transform:uppercase;
  letter-spacing:0.5px; border-bottom:1px solid {T['border']}; font-weight:700; }}
.dt th:first-child, .dt td:first-child {{ text-align:left; }}
.dt td {{ padding:8px 10px; border-bottom:1px solid {T['grid']}; font-family:'SF Mono','Consolas',monospace; color:{T['text']}; }}
.dt tr:hover td {{ background:{T['panel2']}; }}
.best {{ color:{T['up']}; font-weight:700; }}
.worst {{ color:{T['down']}; }}

/* AI 박스 */
.ai {{ background:{T['panel2']}; border:1px solid {T['border']}; border-left:3px solid {T['accent']};
  border-radius:6px; padding:14px; font-size:12.5px; line-height:1.7; color:{T['text']}; white-space:pre-wrap; }}

/* 뉴스 */
.news {{ padding:9px 0; border-bottom:1px solid {T['grid']}; }}
.news:last-child {{ border:none; }}
.news a {{ font-size:12px; color:{T['text']}; text-decoration:none; }}
.news a:hover {{ color:{T['accent']}; }}
.news-t {{ font-size:10px; color:{T['text3']}; font-family:'SF Mono','Consolas',monospace; }}
.tag {{ font-size:9px; padding:2px 7px; border-radius:4px; font-weight:700; }}
.tag-h {{ background:color-mix(in srgb,{T['down']} 15%,transparent); color:{T['down']}; }}
.tag-w {{ background:color-mix(in srgb,{GOLD} 18%,transparent); color:{GOLD}; }}
.tag-p {{ background:color-mix(in srgb,{T['up']} 15%,transparent); color:{T['up']}; }}

/* 시뮬레이터 결과 카드 */
.sim-result {{ background:{T['panel2']}; border:1px solid {T['border']}; border-radius:8px; padding:16px; text-align:center; }}
.sim-label {{ font-size:11px; color:{T['text2']}; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px; }}
.sim-big {{ font-size:30px; font-weight:800; font-family:'SF Mono','Consolas',monospace; letter-spacing:-1px; }}
.sim-sub {{ font-size:11px; color:{T['text3']}; margin-top:4px; }}
.placeholder {{ background:{T['panel2']}; border:1px dashed {T['border']}; border-radius:8px;
  display:flex; flex-direction:column; align-items:center; justify-content:center; height:240px; color:{T['text3']}; font-size:13px; gap:8px; }}
.summary-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:12px; }}
.summary-card {{ background:{T['panel2']}; border:1px solid {T['border']}; border-radius:8px; padding:12px 14px; min-height:96px; }}
.summary-k {{ color:{T['text3']}; font-size:10px; font-weight:800; letter-spacing:0.6px; text-transform:uppercase; margin-bottom:7px; }}
.summary-v {{ color:{T['text']}; font-size:13px; line-height:1.55; }}
.report-note {{ color:{T['text2']}; font-size:12px; line-height:1.6; margin-bottom:12px; }}

/* 입력 위젯 */
[data-testid="stNumberInput"] label, [data-testid="stTextInput"] label {{ color:{T['text2']} !important; font-size:11px !important; font-weight:600; }}
[data-testid="stNumberInput"] input, [data-testid="stTextInput"] input {{
  background:{T['panel2']} !important; color:{T['text']} !important; border:1px solid {T['border']} !important; font-size:13px !important; font-family:'SF Mono','Consolas',monospace; }}
.stButton button {{ background:{T['accent']}; color:#fff; border:none; border-radius:7px; font-weight:600; font-size:12px; }}
.stButton button:hover {{ filter:brightness(1.1); color:#fff; border:none; }}
div[data-baseweb="select"] > div {{ background:{T['panel2']}; border-color:{T['border']}; }}
[data-testid="stMetricValue"] {{ font-family:'SF Mono','Consolas',monospace; color:{T['text']}; }}
[data-testid="stMetricLabel"] {{ color:{T['text2']}; }}
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 데이터 로직 (app_v5 재활용)
# ════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def get_fred(series_id, name):
    url = (f"https://api.stlouisfed.org/fred/series/observations"
           f"?series_id={series_id}&api_key={api_key}&file_type=json"
           f"&observation_start=2019-01-01")
    try:
        r = requests.get(url, timeout=10)
        obs = r.json()["observations"]
        df = pd.DataFrame(obs)[["date", "value"]]
        df["date"] = pd.to_datetime(df["date"])
        df[name] = pd.to_numeric(df["value"], errors="coerce")
        return df[["date", name]]
    except Exception as e:
        return pd.DataFrame({"date": [datetime.now()], name: [0]})

@st.cache_data(ttl=3600)
def get_exchange_rate():
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", timeout=10)
        return r.json()["rates"]["KRW"]
    except Exception:
        return 1380

def latest(df, col):
    s = df[col].dropna()
    return s.iloc[-1] if len(s) else 0

def delta_pct(df, col, periods=1):
    s = df[col].dropna()
    if len(s) < periods + 1:
        return 0
    return (s.iloc[-1] - s.iloc[-1-periods]) / s.iloc[-1-periods] * 100

def asof_value(df, col, target_date):
    sub = df[(df["date"] <= target_date) & (df[col].notna()) & (df[col] > 0)]
    if len(sub) == 0:
        return None, None
    row = sub.iloc[-1]
    return row[col], row["date"]

def pct_change(current, previous):
    if previous in (None, 0) or current is None:
        return None
    return (current - previous) / previous * 100

def fmt_change(value):
    if value is None:
        return '<span class="fl">N/A</span>'
    cls = "up" if value > 0 else "dn" if value < 0 else "fl"
    sign = "+" if value > 0 else ""
    return f'<span class="{cls}">{sign}{value:.1f}%</span>'

def build_market_compare_rows(rows):
    html_rows = ""
    for r in rows:
        html_rows += (
            "<tr>"
            f"<td>{r['label']}</td>"
            f"<td>{r['unit']}</td>"
            f"<td>{r['date']}</td>"
            f"<td>{r['current']}</td>"
            f"<td>{r['prev_month']}</td>"
            f"<td>{r['mom']}</td>"
            f"<td>{r['prev_year']}</td>"
            f"<td>{r['yoy']}</td>"
            "</tr>"
        )
    return html_rows

def build_market_summary(v_housing, d_housing, v_mortgage, d_mortgage, v_cpi, d_cpi,
                         v_fedfunds, usd_krw, v_wti, d_wti):
    demand = (
        "주택착공이 전월 대비 개선되어 바닥재 수요 환경은 우호적으로 해석됩니다."
        if d_housing > 0 else
        "주택착공이 전월 대비 둔화되어 단기 수요 회복 속도는 보수적으로 볼 필요가 있습니다."
    )
    rate = (
        "모기지 금리 상승은 주택 거래와 리모델링 심리에 부담으로 작용할 수 있습니다."
        if d_mortgage > 0 else
        "모기지 금리 하락은 주택 수요와 리모델링 심리에 완화 요인으로 작용할 수 있습니다."
    )
    cost = (
        "유가 상승은 PVC, 운임, 에너지성 비용에 부담 요인으로 연결될 수 있습니다."
        if d_wti > 0 else
        "유가 안정은 원재료와 물류비 부담 완화에 긍정적입니다."
    )
    fx = (
        "USD/KRW가 높은 구간에 있어 원화 기준 매출에는 우호적이나, 달러화 비용과 견적 민감도 점검이 필요합니다."
        if usd_krw >= 1400 else
        "USD/KRW가 상대적으로 안정적이어서 환율 민감도는 관리 가능한 구간으로 보입니다."
    )
    headline = (
        f"현재 미국 주택 지표는 {v_housing:,.0f}K, 30년 모기지 금리는 {v_mortgage:.2f}%입니다. "
        f"CPI {v_cpi:.1f}, 기준금리 {v_fedfunds:.2f}%, USD/KRW {usd_krw:,.0f}원 기준으로 가격과 수요를 함께 점검해야 합니다."
    )
    actions = [
        "주요 거래선 견적은 환율과 운임 변동을 반영해 유효기간을 짧게 관리",
        "미국 주택 지표 둔화 시 프로모션 대상 지역과 제품 믹스 재점검",
        "유가와 운임 상승 구간에서는 선적 일정과 재고 회전율을 우선 확인",
    ]
    return {
        "headline": headline,
        "demand": demand,
        "rate": rate,
        "cost": cost,
        "fx": fx,
        "actions": actions,
    }

def create_pdf_report(metrics, summary, ai_briefing=""):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    buffer = BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=14*mm, leftMargin=14*mm,
        topMargin=13*mm, bottomMargin=12*mm
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "KTitle", parent=styles["Title"], fontName="HYGothic-Medium",
        fontSize=17, leading=22, textColor=colors.HexColor("#0E2372"),
        spaceAfter=5
    )
    sub = ParagraphStyle(
        "KSub", parent=styles["Normal"], fontName="HYGothic-Medium",
        fontSize=8.5, leading=12, textColor=colors.HexColor("#5A6677"),
        spaceAfter=8
    )
    head = ParagraphStyle(
        "KHead", parent=styles["Heading2"], fontName="HYGothic-Medium",
        fontSize=11, leading=14, textColor=colors.HexColor("#0F1722"),
        spaceBefore=5, spaceAfter=5
    )
    body = ParagraphStyle(
        "KBody", parent=styles["BodyText"], fontName="HYGothic-Medium",
        fontSize=9.2, leading=13.5, textColor=colors.HexColor("#202A38")
    )
    small = ParagraphStyle(
        "KSmall", parent=body, fontSize=8.3, leading=12,
        textColor=colors.HexColor("#3E4A5A")
    )

    story = [
        Paragraph("KCC Glass LVT Market Brief", title),
        Paragraph(f"Executive one-page report | {datetime.now().strftime('%Y-%m-%d %H:%M')} 기준", sub),
        Paragraph("1. 핵심 요약", head),
        Paragraph(summary["headline"], body),
        Spacer(1, 5),
    ]

    table_data = [["지표", "현재값", "변화/비고"]]
    for row in metrics:
        table_data.append(row)
    table = Table(table_data, colWidths=[42*mm, 42*mm, 85*mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "HYGothic-Medium"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0E2372")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("FONTSIZE", (0, 1), (-1, -1), 8.2),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E0EA")),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F7F9FC")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.extend([Paragraph("2. 주요 지표", head), table, Spacer(1, 6)])

    story.extend([
        Paragraph("3. 시장 해석", head),
        Paragraph(f"- 수요: {summary['demand']}", small),
        Paragraph(f"- 금리: {summary['rate']}", small),
        Paragraph(f"- 비용: {summary['cost']}", small),
        Paragraph(f"- 환율: {summary['fx']}", small),
        Spacer(1, 5),
        Paragraph("4. 영업 액션 포인트", head),
    ])
    for action in summary["actions"]:
        story.append(Paragraph(f"- {action}", small))

    if ai_briefing:
        clean_brief = str(ai_briefing).replace("\n", "<br/>")
        story.extend([Spacer(1, 5), Paragraph("5. AI 브리핑 메모", head), Paragraph(clean_brief[:900], small)])

    doc.build(story)
    buffer.seek(0)
    return buffer

def calc_landing_cost(invoice, reciprocal_on, reciprocal_rate,
                      mpf_on, mpf_rate, hmf_rate, base_duty_rate,
                      ocean_freight, busan_local, destination, surcharge,
                      sqft_per_cntr=24000):
    base_duty  = invoice * base_duty_rate
    reciprocal = invoice * reciprocal_rate if reciprocal_on else 0
    mpf_raw    = invoice * mpf_rate
    mpf        = max(33.58, min(651.50, mpf_raw)) if mpf_on else 0
    hmf        = invoice * hmf_rate
    total_tax  = base_duty + reciprocal + mpf + hmf
    rows = []
    ports = ["Miami, FL", "New York, NY", "Houston, TX", "LAX/LGB", "Savannah, GA"]
    for i, port in enumerate(ports):
        ood   = ocean_freight[i] + busan_local + destination[i]
        sur   = surcharge[i]
        total = ood + sur + total_tax
        rows.append({"Port": port, "O+O+D": ood, "Tax/Duty": total_tax,
                     "실비": sur, "Total": total, "$/Sqft": total / sqft_per_cntr})
    return rows, total_tax

PORTS = ["LAX/LGB", "Miami, FL", "New York, NY", "Houston, TX", "Savannah, GA"]

# ── 거래선 저장/불러오기 (공유 배포용: 브라우저 세션에만 보관) ──────────

# 저장할 시뮬레이터 입력값 키 목록
SIM_KEYS = ['sim_target_price', 'sim_cost', 'sim_qty', 'sim_duty', 'sim_show_cost',
            'sim_freight', 'sim_local', 'sim_dest', 'lc_exchange',
            'sim_tariff_a', 'sim_tariff_b', 'sim_tariff_c']

def load_clients():
    return st.session_state.setdefault("clients", {})

def save_client(name, data):
    clients = load_clients()
    clients[name] = data
    st.session_state.clients = clients
    return True

def delete_client(name):
    clients = load_clients()
    if name in clients:
        del clients[name]
        st.session_state.clients = clients
        return True
    return False

def init_session_state(usd_krw):
    defaults = {
        'lc_invoice': 30000, 'lc_exchange': int(usd_krw), 'lc_sqft': 24000,
        'lc_rec_on': True, 'lc_rec_rate': 10.0,  # 현재 임시관세 10%
        'lc_mpf_on': False, 'lc_mpf_rate': 0.3464, 'lc_hmf_rate': 0.125, 'lc_base_duty': 0.0,
        'lc_ocean': [1423, 2090, 2050, 2500, 2250], 'lc_busan': 195.78,
        'lc_dest': [978, 1021, 1145, 1528, 1813], 'lc_sur': [1165, 1192, 1165, 1192, 1192],
        # 시뮬레이터 기본값
        'sim_target_price': 1.85, 'sim_cost': 1.20, 'sim_qty': 24000,
        'sim_show_cost': True, 'sim_duty': 10.0,
        'sim_tariff_a': 10.0, 'sim_tariff_b': 15.0, 'sim_tariff_c': 25.0,
        'sim_freight': [1423, 2090, 2050, 2500, 2250],
        'sim_local': 195.78, 'sim_dest': [978, 1021, 1145, 1528, 1813],
        # 원자재 수기 입력 (구매팀 지수) — 최근값 + 이력
        'pvc_price': 0.0, 'dotp_price': 0.0,
        'pvc_history': [], 'dotp_history': [],  # [{date, price}, ...]
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

# ── 데이터 로드 ───────────────────────────────────────────────
df_housing  = get_fred('HOUST',        '주택착공')
df_mortgage = get_fred('MORTGAGE30US', '모기지금리')
df_cpi      = get_fred('CPIAUCSL',     'CPI')
df_fedfunds = get_fred('FEDFUNDS',     '기준금리')
df_newsales = get_fred('HSN1F',        '신규주택판매')
df_wti      = get_fred('DCOILWTICO',    'WTI')
df_brent    = get_fred('DCOILBRENTEU',  'Brent')
df_fx       = get_fred('DEXKOUS',       'USD/KRW')
usd_krw     = get_exchange_rate()
init_session_state(usd_krw)

v_housing  = latest(df_housing,  '주택착공')
v_mortgage = latest(df_mortgage, '모기지금리')
v_cpi      = latest(df_cpi,      'CPI')
v_fedfunds = latest(df_fedfunds, '기준금리')
v_wti      = latest(df_wti,      'WTI')
v_brent    = latest(df_brent,    'Brent')
v_fx_hist  = latest(df_fx,       'USD/KRW')
d_housing  = delta_pct(df_housing,  '주택착공')
d_mortgage = delta_pct(df_mortgage, '모기지금리')
d_cpi      = delta_pct(df_cpi,      'CPI')
d_wti      = delta_pct(df_wti,      'WTI')
d_brent    = delta_pct(df_brent,    'Brent')
d_fx       = delta_pct(df_fx,       'USD/KRW', periods=20)

def chart_layout(fig, height=240):
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=T['text2'], size=11),
        margin=dict(l=10, r=60, t=10, b=10), height=height,
        legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(color=T['text2'], size=10),
                    orientation='h', yanchor='bottom', y=1.0, xanchor='left', x=0),
        xaxis=dict(gridcolor=T['chart_grid'], showgrid=False),
        yaxis=dict(gridcolor=T['chart_grid']),
    )
    return fig

# ════════════════════════════════════════════════════════════
# 사이드바
# ════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown('<div class="sb-brand">LVT INTELLIGENCE</div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-sub">KCC Glass · Overseas Sales</div>', unsafe_allow_html=True)
    menu = st.radio("", [
        "📊 Overview", "🛢 원자재", "🚢 Freight",
        "📰 FCW News", "🏡 Housing", "📈 Macro", "💱 FX/Tariff"
    ], label_visibility="collapsed")

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    # 테마 토글
    theme_label = "🌙 다크 모드" if st.session_state.theme == "light" else "☀️ 라이트 모드"
    if st.button(theme_label, use_container_width=True):
        st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
        st.rerun()

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
    fred_ok = "🟢" if api_key and "여기에" not in api_key else "⚪"
    claude_ok = "🟢" if anthropic_key else "⚪"
    st.markdown(f"<div style='font-size:11px;color:#9FB0D9'>{fred_ok} FRED API<br>{claude_ok} Claude AI<br><span style='color:#6678B0'>Updated {datetime.now().strftime('%H:%M')}</span></div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 상단 티커바 (로고는 항상 흰색 - 네이비 배경)
# ════════════════════════════════════════════════════════════
logo_tag = f'<img class="topbar-logo" src="data:image/png;base64,{LOGO_WHITE}"/>' if LOGO_WHITE else '<span style="color:#fff;font-weight:800;font-size:18px">KCC GLASS</span>'

def tk(label, val, cls=""):
    return f'<div class="tk"><span class="tk-l">{label}</span><span class="tk-v {cls}">{val}</span></div>'

scfi_val = st.session_state.get("scfi_now", 2543)
ticker_html = (
    tk("USD/KRW", f"{usd_krw:,.0f}") +
    tk("30Y MTG", f"{v_mortgage:.2f}%") +
    tk("FED FUNDS", f"{v_fedfunds:.2f}%") +
    tk("WTI", f"{v_wti:.1f}", "tk-up" if d_wti > 0 else "tk-dn") +
    tk("CPI", f"{v_cpi:.1f}")
)
st.markdown(f"""
<div class="topbar">
  {logo_tag}
  <div class="ticker">{ticker_html}</div>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 📊 OVERVIEW
# ════════════════════════════════════════════════════════════
if menu == "📊 Overview":
    st.markdown('<div class="sec"><span class="sec-t">Market Overview</span><span class="sec-s">해외영업 시장 분석 · 미국 LVT 수출</span><span class="live"><span class="dot"></span>Live</span></div>', unsafe_allow_html=True)

    def chg(v, unit="%", suffix=""):
        if abs(v) < 0.05:
            return f'<div class="kpi-c fl">— 0.0{unit}</div>'
        cls = "up" if v > 0 else "dn"
        arr = "▲" if v > 0 else "▼"
        return f'<div class="kpi-c {cls}">{arr} {abs(v):.1f}{unit} <span style="color:{T["text3"]}">{suffix}</span></div>'

    st.markdown(f"""
    <div class="kpi-strip">
      <div class="kpi"><div class="kpi-n">Housing Starts</div><div class="kpi-v">{v_housing:,.0f}<span style="font-size:12px;color:{T['text3']}">K</span></div>{chg(d_housing,"%","MoM")}</div>
      <div class="kpi"><div class="kpi-n">30Y Mortgage</div><div class="kpi-v">{v_mortgage:.2f}<span style="font-size:12px;color:{T['text3']}">%</span></div>{chg(d_mortgage,"%p")}</div>
      <div class="kpi"><div class="kpi-n">CPI Index</div><div class="kpi-v">{v_cpi:.1f}</div>{chg(d_cpi,"%")}</div>
      <div class="kpi"><div class="kpi-n">Fed Funds</div><div class="kpi-v">{v_fedfunds:.2f}<span style="font-size:12px;color:{T['text3']}">%</span></div><div class="kpi-c fl">— policy</div></div>
      <div class="kpi"><div class="kpi-n">USD / KRW</div><div class="kpi-v">{usd_krw:,.0f}</div><div class="kpi-c fl">실시간</div></div>
      <div class="kpi"><div class="kpi-n">New Home Sales</div><div class="kpi-v">{latest(df_newsales,'신규주택판매'):,.0f}<span style="font-size:12px;color:{T['text3']}">K</span></div><div class="kpi-c fl">월간</div></div>
    </div>
    """, unsafe_allow_html=True)

    # ── 특정 날짜 지표 조회 ──
    with st.expander("📅 특정 날짜 지표 조회 — 과거 시점의 모든 지표를 한눈에"):
        import datetime as _dt
        min_d = df_housing["date"].min().date() if len(df_housing) else _dt.date(2019,1,1)
        max_d = _dt.date.today()
        q_date = st.date_input("조회할 날짜", value=max_d, min_value=min_d, max_value=max_d, key="lookup_date")
        q_ts = pd.Timestamp(q_date)
        def asof(df, col):
            sub = df[df["date"] <= q_ts].dropna(subset=[col])
            if len(sub) == 0:
                return None, None
            row = sub.iloc[-1]
            return row[col], row["date"]
        items = [
            ("주택착공", df_housing, "주택착공", "K"),
            ("30Y 모기지", df_mortgage, "모기지금리", "%"),
            ("CPI", df_cpi, "CPI", ""),
            ("기준금리", df_fedfunds, "기준금리", "%"),
            ("USD/KRW", df_fx, "USD/KRW", "원"),
            ("WTI", df_wti, "WTI", "$"),
            ("Brent", df_brent, "Brent", "$"),
        ]
        tr = ""
        for label, df, col, unit in items:
            val, dt = asof(df, col)
            if val is not None:
                vtxt = f"{val:,.2f}{unit}" if unit in ("%","$","") else f"{val:,.0f}{unit}"
                tr += f'<tr><td>{label}</td><td>{vtxt}</td><td style="color:{T["text3"]}">{dt.strftime("%Y-%m-%d")} 기준</td></tr>'
        st.markdown(f'<table class="dt"><thead><tr><th>지표</th><th>값</th><th>해당 데이터 일자</th></tr></thead><tbody>{tr}</tbody></table>', unsafe_allow_html=True)
        st.caption("선택한 날짜에 데이터가 없으면, 그 이전 가장 가까운 발표값을 보여줍니다 (지표마다 발표 주기가 달라서요).")

    # 차트 + AI 브리핑
    c1, c2 = st.columns([2, 1], gap="medium")
    with c1:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">US Housing & Mortgage Rate</span><span class="p-m">Starts vs 30Y Rate</span></div><div class="p-body">', unsafe_allow_html=True)
        fig = go.Figure()
        dfh = df_housing.tail(60)
        # 모기지 금리(주간 데이터)를 주택착공과 같은 날짜 범위로 맞춤
        _start = dfh["date"].min()
        dfm = df_mortgage[df_mortgage["date"] >= _start]
        fig.add_trace(go.Bar(x=dfh["date"], y=dfh["주택착공"], name="Housing Starts (K)", marker_color=T['accent'], opacity=0.7))
        fig.add_trace(go.Scatter(x=dfm["date"], y=dfm["모기지금리"], name="30Y Rate (%)", yaxis="y2", line=dict(color=T['down'], width=2.5)))
        _mmin, _mmax = dfm["모기지금리"].min(), dfm["모기지금리"].max()
        _pad = (_mmax - _mmin) * 0.35 if _mmax > _mmin else 1
        # x축 양끝에 여백 추가 (선/막대가 끝에 잘리지 않게)
        _xmin, _xmax = dfh["date"].min(), dfh["date"].max()
        _xspan = (_xmax - _xmin) / len(dfh) * 1.5
        fig.update_layout(
            yaxis2=dict(overlaying="y", side="right", gridcolor='rgba(0,0,0,0)',
                        range=[_mmin - _pad, _mmax + _pad]),
            xaxis=dict(range=[_xmin - _xspan, _xmax + _xspan], gridcolor='rgba(0,0,0,0)', showgrid=False),
        )
        chart_layout(fig, 260)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        st.markdown('</div></div>', unsafe_allow_html=True)

    with c2:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">AI 시장 브리핑</span><span class="p-m">Claude</span></div><div class="p-body">', unsafe_allow_html=True)
        if not anthropic_key:
            st.markdown('<div class="placeholder"><span style="font-size:26px">🤖</span><span>Claude API 키 설정 시 활성화</span></div>', unsafe_allow_html=True)
        elif st.button("📋 브리핑 생성", use_container_width=True, key="brief"):
            with st.spinner("분석 중..."):
                ind = {
                    "30년 모기지 금리": f"{v_mortgage:.2f}% ({d_mortgage:+.1f}%)",
                    "주택착공": f"{v_housing:,.0f}K ({d_housing:+.1f}%)",
                    "CPI": f"{v_cpi:.1f} ({d_cpi:+.1f}%)",
                    "기준금리": f"{v_fedfunds:.2f}%",
                    "USD/KRW": f"{usd_krw:,.0f}원",
                }
                b = llm.generate_market_briefing(anthropic_key, ind)
                st.session_state.market_briefing = b
                st.markdown(f'<div class="ai">{b}</div>', unsafe_allow_html=True)
        elif st.session_state.get("market_briefing"):
            st.markdown(f'<div class="ai">{st.session_state.market_briefing}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="placeholder"><span style="font-size:26px">📋</span><span>버튼을 눌러 브리핑 생성</span></div>', unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">USD/KRW Exchange Rate Trend</span><span class="p-m">FRED DEXKOUS · Real-time marker</span></div><div class="p-body">', unsafe_allow_html=True)
    fx_period = st.radio(
        "USD/KRW 기간",
        ["1년", "3년", "5년"],
        horizontal=True,
        label_visibility="collapsed",
        key="overview_fx_period",
    )
    fx_days = {"1년": 365, "3년": 365 * 3, "5년": 365 * 5}[fx_period]
    dffx = df_fx[df_fx["USD/KRW"] > 0].copy()
    dffx = dffx[dffx["date"] >= (pd.Timestamp.now() - pd.Timedelta(days=fx_days))]
    if len(dffx):
        fig_fx = go.Figure()
        fig_fx.add_trace(go.Scatter(
            x=dffx["date"], y=dffx["USD/KRW"], name="USD/KRW",
            line=dict(color=GOLD, width=2.5),
            fill="tozeroy",
            fillcolor="rgba(232,179,57,0.08)",
            hovertemplate="%{x|%Y-%m-%d}<br>USD/KRW: %{y:,.1f}<extra></extra>",
        ))
        fig_fx.add_hline(
            y=usd_krw, line_width=1, line_dash="dot", line_color=T["accent"],
            annotation_text=f"Live {usd_krw:,.0f}", annotation_position="top right",
        )
        _fymin, _fymax = dffx["USD/KRW"].min(), dffx["USD/KRW"].max()
        _fypad = (_fymax - _fymin) * 0.18 if _fymax > _fymin else 50
        chart_layout(fig_fx, 230)
        fig_fx.update_layout(
            yaxis=dict(range=[_fymin - _fypad, _fymax + _fypad], gridcolor=T['chart_grid']),
            hovermode="x unified",
        )
        st.plotly_chart(fig_fx, use_container_width=True, config={"displayModeBar": False})
        st.markdown(
            f'<div style="color:{T["text3"]};font-size:11px;margin-top:-4px">FRED 일별 환율 흐름에 현재 실시간 환율 {usd_krw:,.0f}원을 점선으로 표시합니다.</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="placeholder"><span style="font-size:26px">💱</span><span>환율 시계열을 불러올 수 없습니다</span></div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

    v_newsales = latest(df_newsales, "신규주택판매")
    market_summary = build_market_summary(
        v_housing, d_housing, v_mortgage, d_mortgage, v_cpi, d_cpi,
        v_fedfunds, usd_krw, v_wti, d_wti
    )
    report_metrics = [
        ["Housing Starts", f"{v_housing:,.0f}K", f"{d_housing:+.1f}% MoM"],
        ["New Home Sales", f"{v_newsales:,.0f}K", "월간 발표"],
        ["30Y Mortgage", f"{v_mortgage:.2f}%", f"{d_mortgage:+.2f}%p"],
        ["CPI Index", f"{v_cpi:.1f}", f"{d_cpi:+.1f}%"],
        ["Fed Funds", f"{v_fedfunds:.2f}%", "정책금리"],
        ["USD/KRW", f"{usd_krw:,.0f}", f"20거래일 {d_fx:+.1f}%"],
        ["WTI", f"${v_wti:.1f}", f"{d_wti:+.1f}%"],
    ]

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Executive Snapshot</span><span class="p-m">Auto summary</span></div><div class="p-body">', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="summary-grid">
      <div class="summary-card"><div class="summary-k">Demand</div><div class="summary-v">{market_summary["demand"]}</div></div>
      <div class="summary-card"><div class="summary-k">Rate</div><div class="summary-v">{market_summary["rate"]}</div></div>
      <div class="summary-card"><div class="summary-k">Cost / FX</div><div class="summary-v">{market_summary["cost"]}<br>{market_summary["fx"]}</div></div>
    </div>
    """, unsafe_allow_html=True)

    r1, r2 = st.columns([2, 1], gap="medium")
    with r1:
        action_rows = "".join([f"<tr><td>{i}</td><td>{a}</td></tr>" for i, a in enumerate(market_summary["actions"], 1)])
        st.markdown(f'<table class="dt"><thead><tr><th>No.</th><th>상부 보고용 액션 포인트</th></tr></thead><tbody>{action_rows}</tbody></table>', unsafe_allow_html=True)
    with r2:
        st.markdown('<div class="report-note">현재 Overview 지표와 요약을 1페이지 보고서 양식으로 저장합니다. AI 브리핑을 먼저 생성하면 PDF 하단에 함께 반영됩니다.</div>', unsafe_allow_html=True)
        pdf_buffer = create_pdf_report(report_metrics, market_summary, st.session_state.get("market_briefing", ""))
        st.download_button(
            "📄 1페이지 PDF 보고서 다운로드",
            data=pdf_buffer,
            file_name=f"kcc_lvt_market_brief_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    st.markdown('</div></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 💰 수익성 시뮬레이터
# ════════════════════════════════════════════════════════════
elif menu == "🛢 원자재":
    st.markdown('<div class="sec"><span class="sec-t">Raw Materials Monitor</span><span class="sec-s">유가 · 환율 통합 모니터링</span><span class="live"><span class="dot"></span>Live</span></div>', unsafe_allow_html=True)

    def chg2(v, unit="%"):
        if abs(v) < 0.05:
            return f'<div class="kpi-c fl">— 0.0{unit}</div>'
        cls = "up" if v > 0 else "dn"
        arr = "▲" if v > 0 else "▼"
        return f'<div class="kpi-c {cls}">{arr} {abs(v):.1f}{unit}</div>'

    st.markdown(f"""
    <div class="kpi-strip" style="grid-template-columns:repeat(3,1fr);">
      <div class="kpi"><div class="kpi-n">WTI 원유</div><div class="kpi-v">{v_wti:,.1f}<span style="font-size:12px;color:{T['text3']}">$</span></div>{chg2(d_wti)}</div>
      <div class="kpi"><div class="kpi-n">Brent 원유</div><div class="kpi-v">{v_brent:,.1f}<span style="font-size:12px;color:{T['text3']}">$</span></div>{chg2(d_brent)}</div>
      <div class="kpi"><div class="kpi-n">USD / KRW</div><div class="kpi-v">{usd_krw:,.0f}</div><div class="kpi-c fl">실시간</div></div>
    </div>
    """, unsafe_allow_html=True)

    # 기간 선택
    period = st.radio("기간", ["1년", "3년", "전체"], horizontal=True, label_visibility="collapsed", key="oil_period")
    period_map = {"1년": 365, "3년": 365*3, "전체": None}
    days = period_map[period]

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">유가 추이 (WTI / Brent)</span><span class="p-m">FRED · USD/barrel</span></div><div class="p-body">', unsafe_allow_html=True)
    fig = go.Figure()
    if days:
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
        dfw = df_wti[df_wti["date"] >= cutoff]
        dfb = df_brent[df_brent["date"] >= cutoff]
    else:
        dfw = df_wti; dfb = df_brent
    fig.add_trace(go.Scatter(x=dfw["date"], y=dfw["WTI"], name="WTI", line=dict(color=T['accent'], width=2),
                             hovertemplate="%{x|%Y-%m-%d}<br>WTI: $%{y:.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=dfb["date"], y=dfb["Brent"], name="Brent", line=dict(color=GOLD, width=2),
                             hovertemplate="%{x|%Y-%m-%d}<br>Brent: $%{y:.2f}<extra></extra>"))
    chart_layout(fig, 340)
    fig.update_layout(hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div></div>', unsafe_allow_html=True)

    def raw_compare_row(label, df, col, unit, decimals=1, current_override=None):
        clean = df[(df[col].notna()) & (df[col] > 0)].copy()
        if len(clean) == 0:
            return {
                "label": label, "unit": unit, "date": "N/A", "current": "N/A",
                "prev_month": "N/A", "mom": fmt_change(None),
                "prev_year": "N/A", "yoy": fmt_change(None),
            }
        last = clean.iloc[-1]
        current = current_override if current_override is not None else last[col]
        base_date = pd.Timestamp(last["date"])
        pm, _ = asof_value(clean, col, base_date - pd.DateOffset(months=1))
        py, _ = asof_value(clean, col, base_date - pd.DateOffset(years=1))
        if unit == "$/bbl":
            value_fmt = lambda v: "N/A" if v is None else f"${v:,.{decimals}f}"
        elif unit == "KRW/USD":
            value_fmt = lambda v: "N/A" if v is None else f"{v:,.0f}"
        else:
            value_fmt = lambda v: "N/A" if v is None else f"{v:,.{decimals}f}"
        return {
            "label": label,
            "unit": unit,
            "date": base_date.strftime("%Y-%m-%d"),
            "current": value_fmt(current),
            "prev_month": value_fmt(pm),
            "mom": fmt_change(pct_change(current, pm)),
            "prev_year": value_fmt(py),
            "yoy": fmt_change(pct_change(current, py)),
        }

    raw_rows = [
        raw_compare_row("WTI 원유", df_wti, "WTI", "$/bbl", 1),
        raw_compare_row("Brent 원유", df_brent, "Brent", "$/bbl", 1),
        raw_compare_row("USD/KRW", df_fx, "USD/KRW", "KRW/USD", 0, current_override=usd_krw),
    ]
    raw_table = build_market_compare_rows(raw_rows)
    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">원자재 핵심 지표 비교표</span><span class="p-m">Current vs 1M / 1Y</span></div><div class="p-body">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <table class="dt">
          <thead>
            <tr>
              <th>지표</th><th>단위</th><th>기준일</th><th>현재</th>
              <th>전월</th><th>전월대비</th><th>전년</th><th>전년대비</th>
            </tr>
          </thead>
          <tbody>{raw_table}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )
    st.caption("전월/전년 값은 해당 기준일 이전의 가장 가까운 발표값 기준입니다. USD/KRW 현재값은 실시간 환율, 비교값은 FRED 일별 고시 흐름 기준입니다.")
    st.markdown('</div></div>', unsafe_allow_html=True)
# ════════════════════════════════════════════════════════════
elif menu == "🚢 Freight":
    st.markdown('<div class="sec"><span class="sec-t">Freight & Logistics</span><span class="sec-s">운임 뉴스 · AI 위험도 분석</span></div>', unsafe_allow_html=True)
    cN, cA = st.columns([1, 1], gap="medium")
    with cN:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">📰 물류·운임 뉴스</span><span class="p-m">Google News RSS</span></div><div class="p-body">', unsafe_allow_html=True)
        news = llm.fetch_news("freight", limit=8)
        if news:
            for n in news:
                pub = n['published'][:16] if n['published'] else ""
                st.markdown(f'<div class="news"><a href="{n["link"]}" target="_blank">{n["title"]}</a><div class="news-t">{pub}</div></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="placeholder"><span style="font-size:26px">📡</span><span>뉴스를 불러올 수 없습니다</span></div>', unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)
    with cA:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">🤖 AI 운임 분석</span><span class="p-m">Claude · LVT 수출 관점</span></div><div class="p-body">', unsafe_allow_html=True)
        if not anthropic_key:
            st.markdown('<div class="placeholder"><span style="font-size:26px">🤖</span><span>Claude API 키 설정 시 활성화</span></div>', unsafe_allow_html=True)
        elif st.button("🔍 AI 분석 실행", use_container_width=True):
            with st.spinner("분석 중..."):
                a = llm.analyze_freight_news(anthropic_key, news)
                st.markdown(f'<div class="ai">{a}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="placeholder"><span style="font-size:26px">🔍</span><span>버튼을 눌러 분석 시작</span></div>', unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 📰 FCW NEWS
# ════════════════════════════════════════════════════════════
elif menu == "📰 FCW News":
    st.markdown('<div class="sec"><span class="sec-t">Floor Covering Weekly</span><span class="sec-s">바닥재 산업 최신 기사 · FCW</span><span class="live"><span class="dot"></span>Live</span></div>', unsafe_allow_html=True)

    fcw_category = st.radio(
        "FCW Category",
        ["All Latest", "Features", "Products", "Retail", "Business Builder", "Sustainability", "Technology", "Style & Design"],
        horizontal=True,
        label_visibility="collapsed",
        key="fcw_category",
    )
    fcw_items = llm.fetch_fcw_news(fcw_category, limit=14)

    left, right = st.columns([2, 1], gap="medium")
    with left:
        st.markdown(f'<div class="panel"><div class="p-head"><span class="p-t">Latest Articles</span><span class="p-m">{fcw_category}</span></div><div class="p-body">', unsafe_allow_html=True)
        for item in fcw_items:
            title = html.escape(item.get("title", ""))
            link = html.escape(item.get("link", ""))
            published = html.escape(item.get("published", ""))
            summary = html.escape(item.get("summary", ""))
            date_html = f"<span>{published}</span>" if published else "<span>Latest</span>"
            summary_html = f"<div style='font-size:11px;color:{T['text2']};line-height:1.55;margin-top:4px'>{summary}</div>" if summary else ""
            st.markdown(
                f"""
                <div class="news">
                  <a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>
                  <div class="news-t">{date_html} · Floor Covering Weekly</div>
                  {summary_html}
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.markdown('</div></div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Industry Watch</span><span class="p-m">Use case</span></div><div class="p-body">', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="summary-grid" style="grid-template-columns:1fr;">
              <div class="summary-card"><div class="summary-k">Why FCW</div><div class="summary-v">미국 바닥재 업계의 제품, 리테일, 시공, 지속가능성, 기술 동향을 빠르게 확인하는 용도로 볼 수 있습니다.</div></div>
              <div class="summary-card"><div class="summary-k">Sales Signal</div><div class="summary-v">LVT, resilient, retail, builder 관련 기사는 미국 거래선 미팅 전 시장 분위기 체크에 활용하기 좋습니다.</div></div>
              <div class="summary-card"><div class="summary-k">Refresh</div><div class="summary-v">기사 목록은 약 30분 단위로 갱신됩니다. 원문 제목을 누르면 FCW 사이트가 새 창으로 열립니다.</div></div>
            </div>
            <a href="https://www.floorcoveringweekly.com/" target="_blank" rel="noopener noreferrer" style="color:{T['accent']};font-size:12px;text-decoration:none;font-weight:700;">FCW 원문 사이트 열기 →</a>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('</div></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 🏡 HOUSING
# ════════════════════════════════════════════════════════════
elif menu == "🏡 Housing":
    st.markdown('<div class="sec"><span class="sec-t">US Housing Market</span><span class="sec-s">주택착공 · 신규주택판매 · 모기지 금리</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Housing Starts & New Home Sales</span><span class="p-m">2019–Present</span></div><div class="p-body">', unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_housing["date"], y=df_housing["주택착공"], name="Housing Starts (K)", line=dict(color=T['accent'], width=2)))
    fig.add_trace(go.Scatter(x=df_newsales["date"], y=df_newsales["신규주택판매"], name="New Home Sales (K)", line=dict(color=GOLD, width=2)))
    chart_layout(fig, 320)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 📈 MACRO
# ════════════════════════════════════════════════════════════
elif menu == "📈 Macro":
    st.markdown('<div class="sec"><span class="sec-t">Macro Indicators</span><span class="sec-s">CPI · 기준금리</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">CPI & Fed Funds Rate</span><span class="p-m">2019–Present</span></div><div class="p-body">', unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_cpi["date"], y=df_cpi["CPI"], name="CPI", line=dict(color=GOLD, width=2)))
    fig.add_trace(go.Scatter(x=df_fedfunds["date"], y=df_fedfunds["기준금리"], name="Fed Funds (%)", yaxis="y2", line=dict(color=T['accent'], width=2, dash="dot")))
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", gridcolor='rgba(0,0,0,0)'))
    chart_layout(fig, 320)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 💱 FX/TARIFF
# ════════════════════════════════════════════════════════════
elif menu == "💱 FX/Tariff":
    st.markdown('<div class="sec"><span class="sec-t">FX & Tariff</span><span class="sec-s">환율 · 관세 현황</span></div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1: st.metric("USD / KRW", f"{usd_krw:,.0f}")
    with c2: st.metric("관세율 (임시)", f"{st.session_state.sim_duty:.0f}%")
    with c3: st.metric("기본 관세 (FTA)", "0%")
    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">📋 LVT 관세 참고 (미국 수입)</span><span class="p-m">실무 참고용</span></div><div class="p-body">', unsafe_allow_html=True)
    tref = pd.DataFrame([
        {"구분": "HTS 코드", "내용": "3918.10 (비닐 바닥재)", "비고": "품목분류 변동 가능"},
        {"구분": "한미 FTA", "내용": "기본 관세 0%", "비고": "원산지증명(CO) 필요"},
        {"구분": "임시 관세", "내용": f"{st.session_state.sim_duty:.0f}% (현재)", "비고": "정책 변동 모니터링"},
        {"구분": "MPF", "내용": "0.3464% (Min $33.58/Max $651.50)", "비고": "CO 보완 시 면제 가능"},
        {"구분": "HMF", "내용": "0.125%", "비고": "해상운송 부과"},
    ])
    st.dataframe(tref, use_container_width=True, hide_index=True)
    st.caption("⚠️ 참고용 · 실제 통관 시 관세사·세관 확인 필요")
    st.markdown('</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">📰 관세·무역 뉴스</span><span class="p-m">RSS</span></div><div class="p-body">', unsafe_allow_html=True)
    tnews = llm.fetch_news("tariff", limit=6)
    if tnews:
        for n in tnews:
            pub = n['published'][:16] if n['published'] else ""
            st.markdown(f'<div class="news"><a href="{n["link"]}" target="_blank">{n["title"]}</a><div class="news-t">{pub}</div></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div style="color:{T["text3"]};font-size:12px;padding:10px 0">뉴스를 불러올 수 없습니다.</div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 🧮 LANDING COST
# ════════════════════════════════════════════════════════════
