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
from io import BytesIO
import os
import base64
import html
import json
import re
from urllib.parse import quote

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
google_places_key = get_secret("GOOGLE_PLACES_API_KEY", "")

# ── 로고 로드 ─────────────────────────────────────────────────
def _logo(path):
    try:
        with open(os.path.join(os.path.dirname(__file__), path), "rb") as f:
            return base64.b64encode(f.read()).decode()
    except Exception:
        return ""
LOGO_WHITE = _logo("logo_white_t.png")  # 다크 헤더용 (항상 사용 - 헤더가 네이비)
LOGO_NAVY  = _logo("logo_navy_t.png")   # 라이트 모드 대비용

# ── 공식 ESG 리소스 링크 (PDF 파일은 앱에 저장하지 않고 공식 홈페이지 다운로드 URL만 연결) ──
KCC_ESG_REPORT_PAGE_KO = "https://www.kccglass.co.kr/esgManagement/about/report.do"
KCC_ESG_REPORT_PAGE_EN = "https://www.kccglass.co.kr/eng/esgManagement/about/report.do"

def official_doc_url(file_name, file_real_name):
    return (
        "https://www.kccglass.co.kr/fileDownload.do?flag="
        f"&filePath=/data/docs/{quote(file_name)}"
        f"&fileNm={quote(file_real_name)}"
    )

KCC_ESG_LATEST_KO_URL = official_doc_url("ESG_REPORT_KCCGLASS_2024-2025_07_01.pdf", "ESG_보고서_KCCGLASS")
KCC_ESG_LATEST_EN_URL = official_doc_url("ESG_REPORT_KCCGLASS_ENG_2024-2025_07_01.pdf", "ESG_REPORT_KCCGLASS_ENG")

ESG_SUMMARY_ITEMS = [
    {
        "axis": "Environment",
        "message": "환경·안전·보건 체계를 중심으로 사업장 운영과 제품 전 과정에서 지속가능성 리스크를 관리합니다.",
        "use": "친환경 소재, 저탄소 운영, 안전한 제조 기반을 고객 커뮤니케이션의 신뢰 포인트로 활용",
    },
    {
        "axis": "Supply Chain",
        "message": "지속가능한 공급망 관리 관점에서 협력사와의 책임 있는 조달 및 품질 안정성을 강조합니다.",
        "use": "미국 바이어의 공급망/ESG 질문 대응 시 안정적 파트너십 근거로 활용",
    },
    {
        "axis": "Customer Satisfaction",
        "message": "품질, 서비스, 고객만족 경영을 ESG 체계 안에서 함께 관리하는 구조를 제시합니다.",
        "use": "LVT 제안 시 품질관리와 사후 대응 체계를 회사 신뢰자료로 연결",
    },
    {
        "axis": "Social Contribution",
        "message": "지역사회, 임직원, 이해관계자와 함께하는 지속가능한 성장 방향을 제시합니다.",
        "use": "대외 제안서나 회사 소개 자료에서 기업 책임/브랜드 신뢰 메시지로 활용",
    },
]

# ── 테마 상태 ─────────────────────────────────────────────────
if "theme" not in st.session_state:
    st.session_state.theme = "dark"
if "font_size_mode" not in st.session_state:
    st.session_state.font_size_mode = "기본"

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
FONT_SCALE = {"기본": 1.0, "크게": 1.12, "아주 크게": 1.24}.get(st.session_state.font_size_mode, 1.0)

def fs(px):
    return round(px * FONT_SCALE, 2)

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
.sb-nav-label {{ color:#9FB0D9 !important; font-size:10px; font-weight:900; letter-spacing:.8px; text-transform:uppercase; margin:12px 0 6px 0; }}
.sb-subnav {{ color:#9FB0D9 !important; font-size:10px; line-height:1.45; margin:2px 0 8px 0; }}
.sb-active-page {{ background:rgba(255,255,255,.12); border-left:3px solid {GOLD}; border-radius:7px; padding:7px 9px; margin:4px 0 7px 0; color:#fff !important; font-size:12px; font-weight:900; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{ padding:7px 10px; border-radius:7px; margin:1px 0; font-size:13px; transition:background 0.15s; }}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background:rgba(255,255,255,0.08); }}
[data-testid="stSidebar"] [data-testid="stExpander"] {{ border:1px solid rgba(255,255,255,.12) !important; border-radius:9px !important; background:rgba(255,255,255,.035) !important; margin-bottom:8px; overflow:hidden; box-shadow:none !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] details {{ background:rgba(255,255,255,.035) !important; border:none !important; box-shadow:none !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] details summary {{ padding:8px 10px !important; font-weight:900 !important; background:rgba(255,255,255,.035) !important; border:none !important; box-shadow:none !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] details[open] summary {{ background:rgba(255,255,255,.08) !important; border-bottom:1px solid rgba(255,255,255,.10) !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] details summary:hover {{ background:rgba(255,255,255,.12) !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] details summary p {{ color:#fff !important; font-size:12px !important; font-weight:900 !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpanderDetails"] {{ background:rgba(255,255,255,.035) !important; border:none !important; padding:8px 10px 10px 10px !important; }}
[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stVerticalBlock"] {{ background:transparent !important; }}
[data-testid="stSidebar"] .stButton button {{ background:rgba(255,255,255,.06) !important; color:#DDE6FF !important; border:1px solid rgba(255,255,255,.10) !important; border-radius:7px !important; min-height:34px !important; text-align:left !important; justify-content:flex-start !important; font-size:12px !important; font-weight:800 !important; }}
[data-testid="stSidebar"] .stButton button:hover {{ background:rgba(255,255,255,.13) !important; color:#fff !important; border-color:rgba(232,179,57,.55) !important; }}

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
.p-head {{ padding:11px 14px; border-bottom:1px solid {T['border']}; display:flex; justify-content:space-between; align-items:center;
  background:linear-gradient(90deg,color-mix(in srgb,{NAVY} 34%,{T['panel2']}),color-mix(in srgb,{T['panel2']} 88%,{T['bg']}));
  border-left:3px solid {GOLD}; }}
.p-t {{ font-size:12px; font-weight:800; letter-spacing:0.2px; color:{T['text']}; }}
.p-m {{ font-size:10px; color:{T['text2']}; font-family:'SF Mono','Consolas',monospace; }}
.p-guide {{ padding:9px 14px; border-bottom:1px solid {T['border']}; background:color-mix(in srgb,{T['panel2']} 88%,{T['bg']});
  color:{T['text2']}; font-size:12px; line-height:1.55; }}
.p-guide b {{ color:{GOLD}; font-weight:900; }}
.p-body {{ padding:14px; }}

/* 데이터 테이블 */
.dt {{ width:100%; border-collapse:collapse; font-size:12px; }}
.dt th {{ text-align:right; padding:7px 10px; font-size:10px; color:{T['text3']}; text-transform:uppercase;
  letter-spacing:0.5px; border-bottom:1px solid {T['border']}; font-weight:700; }}
.dt th:first-child, .dt td:first-child {{ text-align:left; }}
.dt td {{ padding:8px 10px; border-bottom:1px solid {T['grid']}; font-family:'SF Mono','Consolas',monospace; color:{T['text']}; }}
.dt tr:hover td {{ background:{T['panel2']}; }}
.table-scroll {{ max-height:360px; overflow:auto; border:1px solid {T['border']}; border-radius:8px; margin-bottom:12px; }}
.table-scroll .dt {{ margin:0; }}
.table-scroll .dt th {{ position:sticky; top:0; background:{T['panel2']}; z-index:1; }}
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
.fcw-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:14px; }}
.fcw-card {{ background:{T['panel2']}; border:1px solid {T['border']}; border-radius:8px; overflow:hidden; min-height:330px; display:flex; flex-direction:column; transition:transform .15s ease, border-color .15s ease; }}
.fcw-card:hover {{ transform:translateY(-2px); border-color:{T['accent']}; }}
.fcw-card.featured {{ display:grid; grid-template-columns:1.05fr 1.35fr; min-height:260px; margin-bottom:14px; }}
.fcw-media {{ height:150px; background:{T['grid']}; overflow:hidden; }}
.fcw-card.featured .fcw-media {{ height:100%; min-height:260px; }}
.fcw-media img {{ width:100%; height:100%; object-fit:cover; display:block; }}
.fcw-fallback {{ width:100%; height:100%; display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg,{NAVY},#24304A 56%,{GOLD}); color:white; font-size:12px; font-weight:800; letter-spacing:1px; }}
.fcw-body {{ padding:14px; display:flex; flex-direction:column; gap:8px; flex:1; }}
.fcw-meta {{ color:{T['text3']}; font-size:11px; font-family:'SF Mono','Consolas',monospace; line-height:1.4; }}
.fcw-title {{ color:{T['text']}; font-size:17px; line-height:1.32; font-weight:800; text-decoration:none; letter-spacing:0; }}
.fcw-title:hover {{ color:{T['accent']}; }}
.fcw-card.featured .fcw-title {{ font-size:22px; line-height:1.25; }}
.fcw-summary {{ color:{T['text2']}; font-size:13px; line-height:1.62; }}
.fcw-read {{ margin-top:auto; color:{T['accent']}; font-size:12px; font-weight:800; text-decoration:none; }}
.freight-stack {{ display:flex; flex-direction:column; gap:12px; }}
.freight-card {{ background:{T['panel2']}; border:1px solid {T['border']}; border-radius:8px; overflow:hidden; display:grid; grid-template-columns:118px 1fr; min-height:128px; transition:transform .15s ease, border-color .15s ease; }}
.freight-card:hover {{ transform:translateY(-2px); border-color:{T['accent']}; }}
.freight-card.featured {{ grid-template-columns:1fr; min-height:230px; }}
.freight-visual {{ background-size:cover; background-position:center; display:flex; flex-direction:column; justify-content:space-between; padding:12px; color:#fff; min-height:128px; }}
.freight-card.featured .freight-visual {{ min-height:118px; }}
.freight-badge {{ font-size:10px; font-weight:900; letter-spacing:1px; color:rgba(255,255,255,.86); text-shadow:0 1px 3px rgba(0,0,0,.6); }}
.freight-mark {{ font-size:24px; font-weight:900; line-height:1; text-shadow:0 2px 8px rgba(0,0,0,.65); }}
.freight-body {{ padding:13px 14px; display:flex; flex-direction:column; gap:7px; }}
.freight-meta {{ color:{T['text3']}; font-size:10px; font-family:'SF Mono','Consolas',monospace; line-height:1.4; }}
.freight-title {{ color:{T['text']}; font-size:15px; line-height:1.35; font-weight:800; text-decoration:none; }}
.freight-card.featured .freight-title {{ font-size:19px; }}
.freight-title:hover {{ color:{T['accent']}; }}
.freight-read {{ margin-top:auto; color:{T['accent']}; font-size:12px; font-weight:800; text-decoration:none; }}
.trend-pill-wrap {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px; }}
.trend-pill {{ display:inline-flex; align-items:center; gap:6px; padding:7px 10px; border:1px solid {T['border']}; border-radius:999px; background:{T['panel2']}; color:{T['text']}; font-size:12px; font-weight:800; }}
.trend-count {{ color:{GOLD}; font-family:'SF Mono','Consolas',monospace; }}
.mood-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; }}
.mood-card {{ position:relative; height:180px; border:1px solid {T['border']}; border-radius:8px; overflow:hidden; background:{T['panel2']}; }}
.mood-card img {{ width:100%; height:100%; object-fit:cover; display:block; filter:saturate(.95) contrast(1.04); }}
.mood-fallback {{ width:100%; height:100%; display:flex; align-items:center; justify-content:center; background:linear-gradient(135deg,#24304A,#0E2372 52%,#E8B339); color:white; font-weight:900; letter-spacing:1px; text-align:center; padding:12px; }}
.mood-overlay {{ position:absolute; left:0; right:0; bottom:0; padding:10px; background:linear-gradient(0deg,rgba(0,0,0,.78),rgba(0,0,0,0)); color:#fff; font-size:12px; font-weight:800; line-height:1.3; }}

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
.alert-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }}
.alert-card {{ background:{T['panel2']}; border:1px solid {T['border']}; border-left:4px solid {T['text3']}; border-radius:8px; padding:12px 14px; min-height:92px; }}
.alert-critical {{ border-left-color:{T['down']}; }}
.alert-warn {{ border-left-color:{GOLD}; }}
.alert-watch {{ border-left-color:{T['accent']}; }}
.alert-level {{ font-size:10px; font-weight:800; letter-spacing:0.7px; text-transform:uppercase; margin-bottom:6px; color:{T['text3']}; }}
.alert-title {{ font-size:13px; font-weight:800; color:{T['text']}; margin-bottom:5px; }}
.alert-msg {{ font-size:12px; color:{T['text2']}; line-height:1.55; }}
.score-pill {{ display:inline-block; min-width:34px; text-align:center; padding:2px 8px; border-radius:999px; font-weight:800; font-size:11px; color:#fff; }}
.score-a {{ background:{T['up']}; }}
.score-b {{ background:{GOLD}; color:#111; }}
.score-c {{ background:{T['text3']}; }}
.watch-grid {{ display:grid; grid-template-columns:repeat(5,1fr); gap:10px; margin-bottom:12px; }}
.watch-card {{ background:{T['panel2']}; border:1px solid {T['border']}; border-radius:8px; padding:12px; min-height:86px; }}
.watch-k {{ color:{T['text3']}; font-size:10px; font-weight:800; text-transform:uppercase; letter-spacing:.6px; margin-bottom:6px; }}
.watch-v {{ color:{T['text']}; font-size:19px; font-family:'SF Mono','Consolas',monospace; font-weight:800; line-height:1.1; }}
.watch-c {{ color:{T['text2']}; font-size:11px; margin-top:6px; }}
.home-hero {{ position:relative; min-height:540px; border-radius:14px; overflow:hidden; margin-bottom:16px;
  background-image:linear-gradient(90deg,rgba(7,11,18,.92) 0%,rgba(7,11,18,.66) 43%,rgba(7,11,18,.20) 100%),
  url('https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1900&q=80');
  background-size:cover; background-position:center; border:1px solid {T['border']}; box-shadow:0 24px 80px rgba(0,0,0,.25); }}
.home-hero::after {{ content:""; position:absolute; inset:-35%; background:linear-gradient(115deg,transparent 0%,rgba(255,255,255,.12) 47%,transparent 54%);
  transform:translateX(-36%); animation:homeSweep 8s ease-in-out infinite; pointer-events:none; z-index:1; }}
@keyframes homeSweep {{ 0%,34%{{transform:translateX(-42%)}} 62%{{transform:translateX(42%)}} 100%{{transform:translateX(42%)}} }}
.home-bg {{ position:absolute; inset:0; background-size:cover; background-position:center; opacity:0; animation:homeSlide 24s infinite; transform:scale(1.04); }}
.home-bg:nth-child(1) {{ background-image:linear-gradient(90deg,rgba(7,11,18,.94),rgba(7,11,18,.62),rgba(7,11,18,.18)), url('https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1900&q=80'); animation-delay:0s; }}
.home-bg:nth-child(2) {{ background-image:linear-gradient(90deg,rgba(7,11,18,.94),rgba(7,11,18,.62),rgba(7,11,18,.18)), url('https://images.unsplash.com/photo-1600566753190-17f0baa2a6c3?auto=format&fit=crop&w=1900&q=80'); animation-delay:6s; }}
.home-bg:nth-child(3) {{ background-image:linear-gradient(90deg,rgba(7,11,18,.94),rgba(7,11,18,.62),rgba(7,11,18,.18)), url('https://images.unsplash.com/photo-1494412519320-aa613dfb7738?auto=format&fit=crop&w=1900&q=80'); animation-delay:12s; }}
.home-bg:nth-child(4) {{ background-image:linear-gradient(90deg,rgba(7,11,18,.94),rgba(7,11,18,.62),rgba(7,11,18,.18)), url('https://images.unsplash.com/photo-1518005020951-eccb494ad742?auto=format&fit=crop&w=1900&q=80'); animation-delay:18s; }}
@keyframes homeSlide {{ 0%{{opacity:0; transform:scale(1.04)}} 7%{{opacity:1}} 27%{{opacity:1; transform:scale(1)}} 34%{{opacity:0}} 100%{{opacity:0}} }}
.home-content {{ position:relative; z-index:2; padding:42px 46px; max-width:1040px; }}
.home-logo {{ height:34px; margin-bottom:42px; }}
.home-eyebrow {{ color:{GOLD}; font-size:12px; font-weight:900; letter-spacing:1.8px; text-transform:uppercase; margin-bottom:12px; }}
.home-title {{ color:#fff; font-size:48px; line-height:1.04; font-weight:900; letter-spacing:0; max-width:760px; margin-bottom:18px; }}
.home-copy {{ color:rgba(255,255,255,.78); font-size:15px; line-height:1.75; max-width:720px; margin-bottom:28px; }}
.home-insight {{ display:inline-flex; align-items:center; gap:9px; max-width:890px; padding:12px 15px; margin-bottom:18px;
  border:1px solid rgba(232,179,57,.38); border-radius:999px; background:rgba(14,35,114,.34); color:#fff; font-size:13px; line-height:1.45; backdrop-filter:blur(10px); }}
.home-insight-badge {{ color:#101827; background:{GOLD}; border-radius:999px; padding:4px 8px; font-size:10px; font-weight:900; letter-spacing:.6px; text-transform:uppercase; white-space:nowrap; }}
.home-metrics {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; max-width:860px; }}
.home-metric {{ background:rgba(12,18,29,.76); border:1px solid rgba(255,255,255,.16); border-radius:9px; padding:13px 14px; backdrop-filter:blur(8px); min-height:128px; }}
.home-metric-k {{ color:rgba(255,255,255,.58); font-size:10px; font-weight:900; letter-spacing:.8px; text-transform:uppercase; margin-bottom:6px; }}
.home-metric-v {{ color:#fff; font-family:'SF Mono','Consolas',monospace; font-size:23px; font-weight:900; line-height:1; }}
.home-metric-c {{ color:rgba(255,255,255,.62); font-size:11px; margin-top:7px; }}
.sparkline {{ width:100%; height:34px; margin-top:10px; display:block; }}
.home-grid {{ display:grid; grid-template-columns:1.15fr .85fr; gap:14px; margin-bottom:14px; }}
.home-entry-grid {{ display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:10px; margin-top:10px; }}
.home-entry {{ background:{T['panel2']}; border:1px solid {T['border']}; border-radius:8px; padding:14px; min-height:142px; position:relative; overflow:hidden; transition:transform .15s ease, border-color .15s ease; }}
.home-entry:hover {{ transform:translateY(-2px); border-color:{T['accent']}; }}
.home-entry::after {{ content:""; position:absolute; right:-34px; top:-34px; width:92px; height:92px; border-radius:50%; background:color-mix(in srgb, {T['accent']} 16%, transparent); }}
.home-entry-icon {{ width:38px; height:38px; display:flex; align-items:center; justify-content:center; border-radius:10px; background:{NAVY}; color:#fff; font-size:19px; margin-bottom:11px; }}
.home-entry-k {{ color:{GOLD}; font-size:10px; font-weight:900; letter-spacing:.8px; text-transform:uppercase; margin-bottom:9px; }}
.home-entry-t {{ color:{T['text']}; font-size:15px; font-weight:900; margin-bottom:8px; }}
.home-entry-d {{ color:{T['text2']}; font-size:12px; line-height:1.55; }}
.home-signal-grid {{ display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }}
.home-signal {{ background:{T['panel2']}; border:1px solid {T['border']}; border-radius:8px; padding:14px; min-height:108px; }}
.home-signal-k {{ color:{T['text3']}; font-size:10px; font-weight:900; letter-spacing:.7px; text-transform:uppercase; margin-bottom:7px; }}
.home-signal-v {{ color:{T['text']}; font-size:13px; line-height:1.65; }}
.home-report-card {{ margin-top:10px; padding:18px; border-radius:10px; border:1px solid color-mix(in srgb, {GOLD} 48%, {T['border']});
  background:linear-gradient(135deg,color-mix(in srgb,{NAVY} 86%,#000),color-mix(in srgb,{T['panel2']} 80%,#000)); position:relative; overflow:hidden; }}
.home-report-card::after {{ content:"PDF"; position:absolute; right:18px; top:14px; color:rgba(255,255,255,.08); font-size:58px; font-weight:900; letter-spacing:-2px; }}
.home-report-k {{ color:{GOLD}; font-size:10px; font-weight:900; letter-spacing:.8px; text-transform:uppercase; margin-bottom:8px; }}
.home-report-t {{ color:#fff; font-size:20px; font-weight:900; margin-bottom:7px; }}
.home-report-d {{ color:rgba(255,255,255,.72); font-size:12px; line-height:1.6; max-width:82%; }}
.home-command-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:14px; }}
.home-command-card {{ background:linear-gradient(135deg,{T['panel2']},color-mix(in srgb,{T['panel']} 78%,#000)); border:1px solid {T['border']}; border-radius:9px; padding:14px; min-height:118px; position:relative; overflow:hidden; box-shadow:0 12px 34px rgba(0,0,0,.10); }}
.home-command-card::after {{ content:""; position:absolute; width:120px; height:120px; right:-62px; bottom:-72px; border-radius:50%; background:color-mix(in srgb,{GOLD} 13%,transparent); }}
.home-command-k {{ color:{T['text3']}; font-size:10px; font-weight:900; letter-spacing:.8px; text-transform:uppercase; margin-bottom:8px; position:relative; z-index:1; }}
.home-command-v {{ color:{T['text']}; font-size:18px; font-weight:900; line-height:1.22; margin-bottom:8px; position:relative; z-index:1; }}
.home-command-c {{ color:{T['text2']}; font-size:12px; line-height:1.55; position:relative; z-index:1; }}
.home-workflow {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:14px; }}
.home-step {{ background:{T['panel']}; border:1px solid {T['border']}; border-radius:8px; padding:12px 13px; display:grid; grid-template-columns:34px 1fr; gap:10px; align-items:start; min-height:86px; }}
.home-step-no {{ width:30px; height:30px; border-radius:50%; background:{NAVY}; color:#fff; display:flex; align-items:center; justify-content:center; font-family:'SF Mono','Consolas',monospace; font-size:11px; font-weight:900; box-shadow:inset 0 -2px 0 rgba(232,179,57,.55); }}
.home-step-t {{ color:{T['text']}; font-size:13px; font-weight:900; margin-bottom:4px; }}
.home-step-d {{ color:{T['text2']}; font-size:11px; line-height:1.45; }}
.esg-card {{ background:linear-gradient(135deg,color-mix(in srgb,#0B3D2E 72%,{T['panel2']}),color-mix(in srgb,#10281F 58%,{T['panel']})); border:1px solid color-mix(in srgb,#22C55E 42%,{T['border']}); border-radius:9px; padding:17px; position:relative; overflow:hidden; margin-bottom:12px; box-shadow:0 18px 42px rgba(0,0,0,.12); }}
.esg-card::after {{ content:"ESG"; position:absolute; right:16px; top:8px; color:rgba(34,197,94,.18); font-size:58px; font-weight:900; letter-spacing:-2px; }}
.esg-k {{ color:#4ADE80; font-size:10px; font-weight:900; letter-spacing:.8px; text-transform:uppercase; margin-bottom:8px; }}
.esg-t {{ color:{T['text']}; font-size:18px; font-weight:900; margin-bottom:8px; }}
.esg-d {{ color:{T['text2']}; font-size:12px; line-height:1.65; max-width:82%; margin-bottom:12px; }}
.esg-tags {{ display:flex; flex-wrap:wrap; gap:7px; margin-bottom:12px; }}
.esg-tag {{ border:1px solid rgba(74,222,128,.26); background:rgba(20,83,45,.28); color:#B7F7C9; border-radius:999px; padding:5px 8px; font-size:10px; font-weight:800; }}
.esg-actions {{ display:flex; flex-wrap:wrap; gap:8px; }}
.esg-btn {{ display:inline-flex; align-items:center; justify-content:center; min-height:34px; padding:8px 11px; border-radius:7px; background:#16A34A; color:#fff !important; font-size:12px; font-weight:900; text-decoration:none !important; }}
.esg-btn.secondary {{ background:rgba(15,23,34,.35); color:#E4E9F0 !important; border:1px solid rgba(74,222,128,.26); }}
.esg-summary-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:9px; margin:12px 0; position:relative; z-index:1; }}
.esg-summary-card {{ background:rgba(8,29,22,.42); border:1px solid rgba(74,222,128,.18); border-radius:8px; padding:11px; min-height:132px; }}
.esg-summary-k {{ color:#86EFAC; font-size:10px; font-weight:900; letter-spacing:.6px; text-transform:uppercase; margin-bottom:7px; }}
.esg-summary-v {{ color:#EEF8F1; font-size:12px; line-height:1.55; margin-bottom:7px; }}
.esg-summary-u {{ color:#A7BDB0; font-size:11px; line-height:1.5; }}
.competitor-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:12px; }}
.competitor-card {{ background:{T['panel2']}; border:1px solid {T['border']}; border-radius:8px; padding:13px; min-height:126px; position:relative; overflow:hidden; }}
.competitor-card::after {{ content:""; position:absolute; width:78px; height:78px; right:-28px; top:-26px; border-radius:50%; background:color-mix(in srgb,{T['accent']} 18%,transparent); }}
.co-logo {{ width:38px; height:38px; border-radius:10px; display:flex; align-items:center; justify-content:center; color:#fff; font-weight:900; font-size:13px; letter-spacing:.5px; margin-bottom:10px; box-shadow:inset 0 0 0 1px rgba(255,255,255,.16); }}
.co-k {{ color:{T['text3']}; font-size:10px; font-weight:900; letter-spacing:.7px; text-transform:uppercase; margin-bottom:4px; }}
.co-name {{ color:{T['text']}; font-size:15px; font-weight:900; margin-bottom:5px; }}
.co-val {{ color:{T['text']}; font-size:22px; font-family:'SF Mono','Consolas',monospace; font-weight:900; line-height:1; }}
.co-sub {{ color:{T['text2']}; font-size:11px; margin-top:7px; line-height:1.45; }}
.co-note {{ color:{T['text3']}; font-size:11px; line-height:1.6; margin-bottom:12px; }}
.co-pill {{ display:inline-flex; align-items:center; gap:6px; padding:5px 8px; border-radius:999px; border:1px solid {T['border']}; background:{T['panel2']}; color:{T['text2']}; font-size:11px; font-weight:800; margin-right:6px; margin-bottom:6px; }}
.account-source-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:12px; }}
.account-source {{ background:{T['panel2']}; border:1px solid {T['border']}; border-radius:8px; padding:13px; min-height:96px; }}
.account-k {{ color:{T['text3']}; font-size:10px; font-weight:900; letter-spacing:.7px; text-transform:uppercase; margin-bottom:7px; }}
.account-v {{ color:{T['text']}; font-size:19px; font-family:'SF Mono','Consolas',monospace; font-weight:900; line-height:1.1; }}
.account-c {{ color:{T['text2']}; font-size:12px; line-height:1.5; margin-top:7px; }}
.account-chip {{ display:inline-flex; align-items:center; gap:6px; padding:5px 8px; border-radius:999px; border:1px solid {T['border']}; background:{T['panel2']}; color:{T['text2']}; font-size:11px; font-weight:800; margin-right:6px; margin-bottom:6px; }}
.upload-done {{ background:color-mix(in srgb,{T['up']} 14%,{T['panel2']}); border:1px solid color-mix(in srgb,{T['up']} 42%,{T['border']}); border-left:4px solid {T['up']}; border-radius:8px; padding:14px 16px; margin:10px 0 14px 0; }}
.upload-done-t {{ color:{T['text']}; font-size:15px; font-weight:900; margin-bottom:7px; }}
.upload-done-d {{ color:{T['text2']}; font-size:12px; line-height:1.6; }}
.upload-wait {{ background:{T['panel']}; border:1px dashed {T['border']}; border-radius:10px; padding:34px 18px; min-height:250px; display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; margin-top:14px; }}
.upload-wait-icon {{ font-size:32px; margin-bottom:10px; }}
.upload-wait-t {{ color:{T['text']}; font-size:18px; font-weight:900; margin-bottom:8px; }}
.upload-wait-d {{ color:{T['text2']}; font-size:13px; line-height:1.7; max-width:720px; }}
.board-grid {{ display:grid; grid-template-columns:1.1fr 1fr 1fr; gap:10px; margin-bottom:12px; }}
.board-card {{ background:{T['panel2']}; border:1px solid {T['border']}; border-radius:8px; padding:14px; min-height:132px; }}
.board-k {{ color:{T['text3']}; font-size:10px; font-weight:900; letter-spacing:.7px; text-transform:uppercase; margin-bottom:8px; }}
.board-v {{ color:{T['text']}; font-size:13px; line-height:1.65; }}
.impact-high {{ color:{T['down']}; font-weight:800; }}
.impact-mid {{ color:{GOLD}; font-weight:800; }}
.impact-low {{ color:{T['up']}; font-weight:800; }}

/* 입력 위젯 */
[data-testid="stNumberInput"] label, [data-testid="stTextInput"] label {{ color:{T['text2']} !important; font-size:11px !important; font-weight:600; }}
[data-testid="stNumberInput"] input, [data-testid="stTextInput"] input {{
  background:{T['panel2']} !important; color:{T['text']} !important; border:1px solid {T['border']} !important; font-size:13px !important; font-family:'SF Mono','Consolas',monospace; }}
.stButton button {{ background:{T['accent']}; color:#fff; border:none; border-radius:7px; font-weight:600; font-size:12px; }}
.stButton button:hover {{ filter:brightness(1.1); color:#fff; border:none; }}
[data-testid="stDownloadButton"] button {{
  background:{T['accent']} !important; color:#fff !important; border:1px solid {T['accent']} !important;
  border-radius:7px !important; font-weight:800 !important; font-size:12px !important;
}}
[data-testid="stDownloadButton"] button:hover {{
  filter:brightness(1.1); color:#fff !important; border-color:{T['accent']} !important;
}}
[data-testid="stDownloadButton"] button * {{ color:#fff !important; }}
div[data-baseweb="select"] > div {{ background:{T['panel2']}; border-color:{T['border']}; }}
[data-testid="stMetricValue"] {{ font-family:'SF Mono','Consolas',monospace; color:{T['text']}; }}
[data-testid="stMetricLabel"] {{ color:{T['text2']}; }}
[data-testid="stRadio"] label p {{ color:{T['text2']} !important; font-weight:700 !important; }}
[data-testid="stRadio"] label span {{ color:{T['text2']} !important; }}
[data-testid="stRadio"] label:hover p {{ color:{T['text']} !important; }}
[data-testid="stRadio"] label:hover span {{ color:{T['text']} !important; }}
[data-testid="stRadio"] [role="radio"][aria-checked="true"] p {{ color:{T['text']} !important; font-weight:800 !important; }}
[data-testid="stRadio"] [role="radio"][aria-checked="true"] span {{ color:{T['text']} !important; }}
[data-testid="stRadio"] [role="radiogroup"] {{ gap:10px; }}

/* 글자 크기 토글 보정 */
[data-testid="stSidebar"] [role="radiogroup"] label {{ font-size:{fs(13)}px !important; }}
.sec-t {{ font-size:{fs(16)}px; }}
.sec-s {{ font-size:{fs(11)}px; }}
.kpi-n {{ font-size:{fs(10)}px; }}
.kpi-v {{ font-size:{fs(21)}px; }}
.kpi-c {{ font-size:{fs(11)}px; }}
.p-t {{ font-size:{fs(12)}px; }}
.p-m {{ font-size:{fs(10)}px; }}
.dt {{ font-size:{fs(12)}px; }}
.dt th {{ font-size:{fs(10)}px; }}
.ai {{ font-size:{fs(12.5)}px; }}
.news a {{ font-size:{fs(12)}px; }}
.news-t {{ font-size:{fs(10)}px; }}
.summary-k {{ font-size:{fs(10)}px; }}
.summary-v {{ font-size:{fs(13)}px; }}
.report-note {{ font-size:{fs(12)}px; }}
.placeholder {{ font-size:{fs(13)}px; }}
[data-testid="stNumberInput"] label, [data-testid="stTextInput"] label {{ font-size:{fs(11)}px !important; }}
[data-testid="stNumberInput"] input, [data-testid="stTextInput"] input {{ font-size:{fs(13)}px !important; }}
.stButton button {{ font-size:{fs(12)}px; }}
[data-testid="stDownloadButton"] button {{ font-size:{fs(12)}px !important; }}
[data-testid="stMetricValue"] {{ font-size:{fs(26)}px !important; }}
[data-testid="stMetricLabel"] {{ font-size:{fs(13)}px !important; }}
[data-testid="stRadio"] label p {{ font-size:{fs(13)}px !important; }}
@media (max-width: 1000px) {{
  .home-hero {{ min-height:560px; }}
  .home-content {{ padding:30px 24px; }}
  .home-title {{ font-size:34px; }}
  .home-metrics, .home-entry-grid, .home-signal-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
  .home-command-grid, .home-workflow {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
  .esg-summary-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
  .home-grid {{ grid-template-columns:1fr; }}
}}
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

def kpi_change(value, unit="%"):
    if value is None or abs(value) < 0.05:
        return f'<div class="kpi-c fl">— 0.0{unit}</div>'
    cls = "up" if value > 0 else "dn"
    arr = "▲" if value > 0 else "▼"
    return f'<div class="kpi-c {cls}">{arr} {abs(value):.1f}{unit}</div>'

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

def format_table_value(v):
    if v is None or pd.isna(v):
        return "-"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return html.escape(str(v))

def table_cell(v, col=None):
    if isinstance(v, str) and ("<span" in v or "<br" in v or "<a " in v):
        return v
    return format_table_value(v)

def dataframe_to_dark_table(df, columns=None, max_rows=None):
    view = df.copy()
    if columns:
        view = view[columns]
    if max_rows:
        view = view.head(max_rows)
    header = "".join(f"<th>{html.escape(str(c))}</th>" for c in view.columns)
    body = ""
    for _, row in view.iterrows():
        body += "<tr>" + "".join(f"<td>{table_cell(row[c], c)}</td>" for c in view.columns) + "</tr>"
    return f'<div class="table-scroll"><table class="dt"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>'

def indicator_compare_row(label, df, col, unit="", decimals=1, current_override=None):
    clean = df[(df[col].notna()) & (df[col] > 0)].copy()
    if len(clean) == 0:
        return {
            "label": label, "unit": unit or "-",
            "date": "N/A", "current": "N/A", "prev_month": "N/A",
            "mom": fmt_change(None), "prev_year": "N/A", "yoy": fmt_change(None),
        }
    last = clean.iloc[-1]
    current = current_override if current_override is not None else last[col]
    base_date = pd.Timestamp(last["date"])
    pm, _ = asof_value(clean, col, base_date - pd.DateOffset(months=1))
    py, _ = asof_value(clean, col, base_date - pd.DateOffset(years=1))

    def value_fmt(v):
        if v is None or pd.isna(v):
            return "N/A"
        if unit == "%":
            return f"{v:,.2f}%"
        if unit == "K":
            return f"{v:,.0f}K"
        if unit == "KRW/USD":
            return f"{v:,.0f}"
        if unit == "$/bbl":
            return f"${v:,.{decimals}f}"
        return f"{v:,.{decimals}f}"

    return {
        "label": label,
        "unit": unit or "-",
        "date": base_date.strftime("%Y-%m-%d"),
        "current": value_fmt(current),
        "prev_month": value_fmt(pm),
        "mom": fmt_change(pct_change(current, pm)),
        "prev_year": value_fmt(py),
        "yoy": fmt_change(pct_change(current, py)),
    }

PURCHASE_PRICE_DEFAULTS = [
    {"월": "2025-01", "PVC": 726.33, "DOTP": 1042.50},
    {"월": "2025-02", "PVC": 717.50, "DOTP": 1025.00},
    {"월": "2025-03", "PVC": 701.75, "DOTP": 1017.00},
    {"월": "2025-04", "PVC": 692.50, "DOTP": 993.75},
    {"월": "2025-05", "PVC": 692.50, "DOTP": 971.25},
    {"월": "2025-06", "PVC": 707.50, "DOTP": 990.00},
    {"월": "2025-07", "PVC": 701.25, "DOTP": 990.00},
    {"월": "2025-08", "PVC": 698.00, "DOTP": 970.00},
    {"월": "2025-09", "PVC": 703.00, "DOTP": 955.00},
    {"월": "2025-10", "PVC": 688.00, "DOTP": 908.33},
    {"월": "2025-11", "PVC": 671.25, "DOTP": 871.25},
    {"월": "2025-12", "PVC": 635.00, "DOTP": 914.00},
    {"월": "2026-01", "PVC": 652.50, "DOTP": 941.25},
    {"월": "2026-02", "PVC": 693.33, "DOTP": 970.00},
    {"월": "2026-03", "PVC": 907.69, "DOTP": 1110.00},
    {"월": "2026-04", "PVC": 1022.50, "DOTP": 1317.50},
    {"월": "2026-05", "PVC": 894.50, "DOTP": 1196.25},
    {"월": "2026-06", "PVC": 817.50, "DOTP": None},
]

def get_purchase_price_df():
    if "purchase_price_rows" not in st.session_state:
        st.session_state.purchase_price_rows = PURCHASE_PRICE_DEFAULTS
    df = pd.DataFrame(st.session_state.purchase_price_rows)
    if "월" not in df.columns:
        df["월"] = pd.Series(dtype="str")
    for col in ["PVC", "DOTP"]:
        if col not in df.columns:
            df[col] = None
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["date"] = pd.to_datetime(df["월"] + "-01", errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return df

def set_purchase_price_df(df):
    clean = df.copy()
    clean["월"] = clean["월"].astype(str).str.slice(0, 7)
    for col in ["PVC", "DOTP"]:
        clean[col] = pd.to_numeric(clean[col], errors="coerce")
    clean["date"] = pd.to_datetime(clean["월"] + "-01", errors="coerce")
    clean = clean.dropna(subset=["date"]).sort_values("date")
    st.session_state.purchase_price_rows = clean[["월", "PVC", "DOTP"]].to_dict("records")
    return get_purchase_price_df()

def purchase_compare_row(label, df, col):
    clean = df[["date", col]].dropna().copy()
    if len(clean) == 0:
        return {
            "label": label, "unit": "구매팀 지수", "date": "N/A", "current": "N/A",
            "prev_month": "N/A", "mom": fmt_change(None),
            "prev_year": "N/A", "yoy": fmt_change(None),
        }
    last = clean.iloc[-1]
    current = last[col]
    base_date = pd.Timestamp(last["date"])
    pm, _ = asof_value(clean, col, base_date - pd.DateOffset(months=1))
    py, _ = asof_value(clean, col, base_date - pd.DateOffset(years=1))
    value_fmt = lambda v: "N/A" if v is None else f"{v:,.2f}"
    return {
        "label": label,
        "unit": "구매팀 지수",
        "date": base_date.strftime("%Y-%m"),
        "current": value_fmt(current),
        "prev_month": value_fmt(pm),
        "mom": fmt_change(pct_change(current, pm)),
        "prev_year": value_fmt(py),
        "yoy": fmt_change(pct_change(current, py)),
    }

def get_freight_index_df():
    if "freight_index_rows" in st.session_state:
        df = pd.DataFrame(st.session_state.freight_index_rows)
        if not df.empty:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            for col in ["SCFI", "CCFI"]:
                if col not in df.columns:
                    df[col] = None
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    path = os.path.join(os.path.dirname(__file__), "freight_index_records.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)
    except Exception:
        records = []
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=["date", "SCFI", "CCFI"])
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ["SCFI", "CCFI"]:
        if col not in df.columns:
            df[col] = None
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)

def freight_compare_row(label, df, col):
    clean = df[["date", col]].dropna().copy()
    if len(clean) == 0:
        return {
            "label": label, "unit": "Index", "date": "N/A", "current": "N/A",
            "prev_month": "N/A", "mom": fmt_change(None),
            "prev_year": "N/A", "yoy": fmt_change(None),
        }
    last = clean.iloc[-1]
    current = last[col]
    base_date = pd.Timestamp(last["date"])
    pm, _ = asof_value(clean, col, base_date - pd.DateOffset(months=1))
    py, _ = asof_value(clean, col, base_date - pd.DateOffset(years=1))
    value_fmt = lambda v: "N/A" if v is None else f"{v:,.2f}"
    return {
        "label": label,
        "unit": "Index",
        "date": base_date.strftime("%Y-%m-%d"),
        "current": value_fmt(current),
        "prev_month": value_fmt(pm),
        "mom": fmt_change(pct_change(current, pm)),
        "prev_year": value_fmt(py),
        "yoy": fmt_change(pct_change(current, py)),
    }

def get_market_insight_df():
    path = os.path.join(os.path.dirname(__file__), "market_insight_records.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            records = json.load(f)
    except Exception:
        records = []
    df = pd.DataFrame(records)
    if df.empty:
        return pd.DataFrame(columns=[
            "category", "type", "rank_2025", "rank_2024", "rank_2023", "rank_2022",
            "company", "home_base", "state", "sales_2025", "sales_2024", "sales_2023", "sales_2022"
        ])
    for col in ["rank_2025", "rank_2024", "rank_2023", "rank_2022", "sales_2025", "sales_2024", "sales_2023", "sales_2022"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    df["state"] = df["state"].astype(str).str.upper()
    return df

COMPETITOR_COLORS = {
    "동신": "#0E2372", "일신": "#2354C6", "kdf": "#2D7FF9", "대진": "#15B86B",
    "녹수": "#E8B339", "서한": "#7C3AED", "kte": "#F0454A", "LX하우시스": "#44546A",
    "KCC": "#0B3D91", "유성": "#009CA6", "현태": "#6B7280", "재영": "#A16207",
    "DSK": "#2563EB", "현대": "#64748B", "모림": "#9333EA", "Wellmark": "#0F766E",
    "서해테크": "#B45309", "General DE": "#475569",
}

SUPPLIER_NAME_MAP = {
    "daejin": "대진",
    "dongshin-polymer": "동신",
    "dsk": "DSK",
    "hyundai": "현대",
    "ilshin-chemical": "일신",
    "jaeyoung": "재영",
    "kcc-glass": "KCC",
    "kdf": "kdf",
    "kte": "kte",
    "lx-hausys": "LX하우시스",
    "moleem": "모림",
    "nox": "녹수",
    "seohae-tech": "서해테크",
    "wellmark": "Wellmark",
    "yousung-c-f": "유성",
    "general-de-productos-exclusivos-s": "General DE",
}

def normalize_supplier_name(value):
    key = str(value).strip().lower()
    key = re.sub(r"\s+", "-", key)
    return SUPPLIER_NAME_MAP.get(key, str(value).strip())

def clean_importer_name(value):
    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("United States of America", "")
    text = text.replace("United States", "")
    text = text.replace("Canada", "")
    text = re.sub(r"\s+", " ", text).strip(" -,_")
    return text or "Unknown"

def company_badge(name):
    label = str(name).strip()
    if label.lower() == "kdf":
        initials = "KDF"
    elif label.lower() == "kte":
        initials = "KTE"
    elif "LX" in label.upper():
        initials = "LX"
    elif label.upper() == "KCC":
        initials = "KCC"
    else:
        initials = label[:2].upper()
    color = COMPETITOR_COLORS.get(label, NAVY)
    return f'<div class="co-logo" style="background:{color}">{html.escape(initials)}</div>'

def get_demo_competitor_export_df():
    months = [f"2025-{m:02d}" for m in range(1, 13)] + ["2026-01"]
    data = {
        "동신": [292467, 133394, 401198, 297844, 2922429, 2932009, 2270563, 3859125, 3369668, 3201123, 2688604, 1595280, 2396704],
        "일신": [0, 0, 0, 0, 0, 0, 3350198, 3463389, 2800604, 3168472, 3651254, 3195522, 2757251],
        "kdf": [0, 0, 0, 0, 0, 380108, 1836829, 1885943, 1786803, 1805083, 1386097, 1609444, 774024],
        "대진": [0, 0, 0, 0, 0, 731240, 773083, 773691, 625358, 739086, 947071, 966721, 194035],
        "녹수": [55289, 50777, 165297, 134641, 1864256, 445700, 595354, 361038, 459888, 597151, 413890, 342408, 186114],
        "서한": [396048, 37620, 79159, 295110, 309962, 257148, 421799, 202600, 625247, 260715, 551951, 609481, 111121],
        "kte": [103230, 154200, 216445, 459031, 258898, 60587, 56762, 451622, 537380, 685278, 550872, 544902, 246642],
        "LX하우시스": [0, 0, 0, 0, 0, 275758, 100564, 264910, 88930, 343900, 297190, 345700, 242640],
        "KCC": [89768, 33487, 59559, 0, 0, 20952, 66176, 134318, 613143, 237702, 66176, 66058, 67160],
        "유성": [34308, 14886, 0, 17173, 35866, 17163, 34326, 34326, 76640, 34326, 52879, 64598, 35283],
        "현태": [0, 0, 0, 0, 0, 0, 51917, 0, 256991, 0, 0, 308908, 38776],
        "재영": [31015, 0, 17500, 22300, 0, 0, 0, 0, 0, 0, 0, 70815, 0],
    }
    rows = []
    for competitor, values in data.items():
        for month, weight in zip(months, values):
            rows.append({"competitor": competitor, "month": month, "weight_kg": float(weight)})
    return pd.DataFrame(rows)

def get_demo_competitor_destination_df():
    rows = [
        ("동신", "Artivo Floors Inc", "United States", "Savannah / Atlanta", 960197),
        ("동신", "Dixie Home Carpets", "United States", "Charleston / Dalton", 612084),
        ("동신", "Tandem Flooring LLC", "United States", "Los Angeles / CA", 277692),
        ("일신", "Interior Logic Group", "United States", "Los Angeles / CA", 1680228),
        ("일신", "Shaw Industries", "United States", "Savannah / GA", 1517002),
        ("일신", "Nox Corporation", "United States", "New York / NJ", 1443794),
        ("kdf", "Bestlaminate", "United States", "Chicago / IL", 711982),
        ("kdf", "Dixie Home Carpets", "United States", "Savannah / GA", 670902),
        ("kdf", "Beaulieu Canada", "Canada", "Vancouver / BC", 626100),
        ("대진", "Happy Feet International", "United States", "Savannah / GA", 451294),
        ("대진", "Raskin Industries", "United States", "New York / NY", 377000),
        ("녹수", "Nox Corporation", "United States", "Savannah / GA", 412973),
        ("녹수", "MSI Surfaces", "United States", "Los Angeles / CA", 303140),
        ("서한", "Ohio Valley Flooring", "United States", "Cincinnati / OH", 497312),
        ("kte", "Go Flooring", "United States", "Los Angeles / CA", 358921),
        ("LX하우시스", "Newport Concepts", "United States", "New York / NJ", 446920),
        ("KCC", "Raskin Industries", "United States", "New York / NY", 210380),
        ("유성", "Adorn Floors", "United States", "Los Angeles / CA", 87652),
        ("현태", "Hyundai L&C USA", "United States", "Atlanta / GA", 347684),
    ]
    return pd.DataFrame(rows, columns=["competitor", "importer", "country", "destination", "weight_kg"])

def normalize_importyeti_raw_upload(uploaded):
    sheets = pd.read_excel(uploaded, sheet_name=None)
    required = {"date", "company", "weight", "supplier"}
    selected = None
    for _, df in sheets.items():
        col_lookup = {str(c).strip().lower(): c for c in df.columns}
        if required.issubset(set(col_lookup.keys())):
            selected = df.rename(columns={v: k for k, v in col_lookup.items()})
            break
    if selected is None:
        raise ValueError("ImportYeti raw 컬럼(date, company, weight, supplier)을 찾지 못했습니다.")

    df = selected.copy()
    for col in ["country", "route", "product_description", "bl_number", "quantity", "value"]:
        if col not in df.columns:
            df[col] = ""
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["month"] = df["date"].dt.strftime("%Y-%m")
    df["weight_kg"] = pd.to_numeric(df["weight"], errors="coerce").fillna(0)
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    df["competitor"] = df["supplier"].map(normalize_supplier_name)
    df["importer"] = df["company"].map(clean_importer_name)
    df["country"] = df["country"].astype(str).str.strip()
    df["destination"] = df["route"].astype(str).str.strip().replace({"": "N/A", "nan": "N/A"})
    df["product_description"] = df["product_description"].astype(str).str.strip()
    df = df.dropna(subset=["date"])
    df = df[(df["competitor"] != "") & (df["weight_kg"] > 0)]

    monthly = (
        df.groupby(["competitor", "month"], as_index=False)
        .agg(weight_kg=("weight_kg", "sum"), shipments=("bl_number", "nunique"), quantity=("quantity", "sum"))
    )
    detail = (
        df.groupby(["competitor", "importer", "country", "destination"], as_index=False)
        .agg(weight_kg=("weight_kg", "sum"), shipments=("bl_number", "nunique"), quantity=("quantity", "sum"))
        .sort_values("weight_kg", ascending=False)
    )
    product = (
        df.groupby(["competitor", "product_description"], as_index=False)
        .agg(weight_kg=("weight_kg", "sum"), shipments=("bl_number", "nunique"))
        .sort_values("weight_kg", ascending=False)
    )
    return monthly, detail, product

def parse_month_col(value):
    text = str(value).strip()
    m = re.search(r"(20\d{2})[-./_년 ]\s*(\d{1,2})", text)
    if not m:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"

def normalize_competitor_upload(uploaded):
    raw = pd.read_excel(uploaded)
    df = raw.copy()
    company_col = None
    for col in df.columns:
        low = str(col).lower()
        if any(k in low for k in ["업체", "회사", "company", "competitor"]):
            company_col = col
            break
    if company_col is None:
        company_col = df.columns[0]
    month_cols = {col: parse_month_col(col) for col in df.columns}
    month_cols = {col: month for col, month in month_cols.items() if month}
    if not month_cols:
        raise ValueError("월별 컬럼(예: 2025-01, 2025년 1월)을 찾지 못했습니다.")
    clean = df[[company_col] + list(month_cols.keys())].copy()
    clean = clean.rename(columns={company_col: "competitor", **month_cols})
    long = clean.melt(id_vars="competitor", var_name="month", value_name="weight_kg")
    long["competitor"] = long["competitor"].astype(str).str.strip()
    long["weight_kg"] = pd.to_numeric(long["weight_kg"], errors="coerce").fillna(0)
    long = long[(long["competitor"] != "") & (long["competitor"].str.lower() != "nan")]
    return long[["competitor", "month", "weight_kg"]]

def get_competitor_export_df():
    if "competitor_export_rows" in st.session_state:
        df = pd.DataFrame(st.session_state.competitor_export_rows)
        if not df.empty:
            df["weight_kg"] = pd.to_numeric(df["weight_kg"], errors="coerce").fillna(0)
            return df
    return pd.DataFrame(columns=["competitor", "month", "weight_kg", "shipments", "quantity"])

def get_competitor_destination_df():
    if "competitor_destination_rows" in st.session_state:
        df = pd.DataFrame(st.session_state.competitor_destination_rows)
        if not df.empty:
            df["weight_kg"] = pd.to_numeric(df["weight_kg"], errors="coerce").fillna(0)
            for col in ["shipments", "quantity"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            return df
    return pd.DataFrame(columns=["competitor", "importer", "country", "destination", "weight_kg", "shipments", "quantity"])

def get_competitor_product_df():
    if "competitor_product_rows" in st.session_state:
        df = pd.DataFrame(st.session_state.competitor_product_rows)
        if not df.empty:
            df["weight_kg"] = pd.to_numeric(df["weight_kg"], errors="coerce").fillna(0)
            if "shipments" in df.columns:
                df["shipments"] = pd.to_numeric(df["shipments"], errors="coerce").fillna(0)
            return df
    return pd.DataFrame(columns=["competitor", "product_description", "weight_kg", "shipments"])

def set_competitor_export_df(df):
    clean = df.copy()
    clean["weight_kg"] = pd.to_numeric(clean["weight_kg"], errors="coerce").fillna(0)
    st.session_state.competitor_export_rows = clean[["competitor", "month", "weight_kg"]].to_dict("records")
    return get_competitor_export_df()

def set_competitor_export_data(monthly_df, detail_df=None, product_df=None):
    clean = monthly_df.copy()
    clean["weight_kg"] = pd.to_numeric(clean["weight_kg"], errors="coerce").fillna(0)
    keep_cols = [c for c in ["competitor", "month", "weight_kg", "shipments", "quantity"] if c in clean.columns]
    st.session_state.competitor_export_rows = clean[keep_cols].to_dict("records")
    if detail_df is not None:
        detail = detail_df.copy()
        detail["weight_kg"] = pd.to_numeric(detail["weight_kg"], errors="coerce").fillna(0)
        detail_cols = [c for c in ["competitor", "importer", "country", "destination", "weight_kg", "shipments", "quantity"] if c in detail.columns]
        st.session_state.competitor_destination_rows = detail[detail_cols].to_dict("records")
    if product_df is not None:
        product = product_df.copy()
        product["weight_kg"] = pd.to_numeric(product["weight_kg"], errors="coerce").fillna(0)
        product_cols = [c for c in ["competitor", "product_description", "weight_kg", "shipments"] if c in product.columns]
        st.session_state.competitor_product_rows = product[product_cols].to_dict("records")
    return get_competitor_export_df()

STATE_CENTERS = {
    "AL": (32.8067, -86.7911), "AZ": (33.7298, -111.4312), "CA": (36.1162, -119.6816),
    "CO": (39.0598, -105.3111), "FL": (27.7663, -81.6868), "GA": (33.0406, -83.6431),
    "ID": (44.2405, -114.4788), "IL": (40.3495, -88.9861), "IN": (39.8494, -86.2583),
    "KS": (38.5266, -96.7265), "LA": (31.1695, -91.8678), "MA": (42.2302, -71.5301),
    "MD": (39.0639, -76.8021), "ME": (44.6939, -69.3819), "MI": (43.3266, -84.5361),
    "MN": (45.6945, -93.9002), "MO": (38.4561, -92.2884), "MS": (32.7416, -89.6787),
    "MT": (46.9219, -110.4544), "NC": (35.6301, -79.8064), "NE": (41.1254, -98.2681),
    "NJ": (40.2989, -74.5210), "NM": (34.8405, -106.2485), "NV": (38.3135, -117.0554),
    "NY": (42.1657, -74.9481), "OH": (40.3888, -82.7649), "OK": (35.5653, -96.9289),
    "OR": (44.5720, -122.0709), "PA": (40.5908, -77.2098), "SC": (33.8569, -80.9450),
    "TN": (35.7478, -86.6923), "TX": (31.0545, -97.5635), "UT": (40.1500, -111.8624),
    "VA": (37.7693, -78.1700), "WA": (47.4009, -121.4905), "WI": (44.2685, -89.6165),
}
CANADA_PROVINCE_CENTERS = {
    "AB": (53.9333, -116.5765), "BC": (53.7267, -127.6476), "MB": (53.7609, -98.8139),
    "NB": (46.5653, -66.4619), "NL": (53.1355, -57.6604), "NS": (44.6820, -63.7443),
    "NT": (64.8255, -124.8457), "NU": (70.2998, -83.1076), "ON": (51.2538, -85.3232),
    "PE": (46.5107, -63.4168), "QC": (52.9399, -73.5491), "SK": (52.9399, -106.4509),
    "YT": (64.2823, -135.0000),
}
REGION_CENTERS = {**STATE_CENTERS, **CANADA_PROVINCE_CENTERS}
US_STATE_CODES = set(STATE_CENTERS.keys())
CA_PROVINCE_CODES = set(CANADA_PROVINCE_CENTERS.keys())
REGION_NAMES = {
    "AL": "Alabama", "AZ": "Arizona", "CA": "California", "CO": "Colorado", "FL": "Florida",
    "GA": "Georgia", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "KS": "Kansas",
    "LA": "Louisiana", "MA": "Massachusetts", "MD": "Maryland", "ME": "Maine", "MI": "Michigan",
    "MN": "Minnesota", "MO": "Missouri", "MS": "Mississippi", "MT": "Montana", "NC": "North Carolina",
    "NE": "Nebraska", "NJ": "New Jersey", "NM": "New Mexico", "NV": "Nevada", "NY": "New York",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania", "SC": "South Carolina",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VA": "Virginia", "WA": "Washington",
    "WI": "Wisconsin", "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba",
    "NB": "New Brunswick", "NL": "Newfoundland and Labrador", "NS": "Nova Scotia",
    "NT": "Northwest Territories", "NU": "Nunavut", "ON": "Ontario", "PE": "Prince Edward Island",
    "QC": "Quebec", "SK": "Saskatchewan", "YT": "Yukon",
}

def infer_region_from_text(value):
    text = str(value or "").upper()
    codes = re.findall(r"\b[A-Z]{2}\b", text)
    for code in reversed(codes):
        if code in REGION_CENTERS:
            return code
    return ""

def infer_country_from_region(region):
    if region in CA_PROVINCE_CODES:
        return "Canada"
    if region in US_STATE_CODES:
        return "United States"
    return "Unknown"

def account_jitter(company, region, index=0):
    seed = sum(ord(ch) for ch in f"{company}-{region}-{index}")
    lat_offset = ((seed % 17) - 8) * 0.055
    lon_offset = (((seed // 17) % 17) - 8) * 0.075
    return lat_offset, lon_offset

def normalize_account_upload(uploaded):
    raw = pd.read_excel(uploaded)
    if raw.empty:
        return pd.DataFrame()
    lookup = {str(c).strip().lower(): c for c in raw.columns}
    aliases = {
        "company": ["company", "업체명", "거래선", "account", "name", "customer", "고객사"],
        "category": ["category", "구분", "분류", "type", "채널"],
        "country": ["country", "국가"],
        "state": ["state", "province", "주", "지역", "state/province"],
        "city": ["city", "도시"],
        "home_base": ["home_base", "home base", "address", "location", "주소", "소재지"],
        "website": ["website", "url", "web", "홈페이지"],
        "notes": ["notes", "note", "메모", "비고"],
        "lat": ["lat", "latitude", "위도"],
        "lon": ["lon", "lng", "longitude", "경도"],
    }
    def pick(name):
        for alias in aliases[name]:
            if alias.lower() in lookup:
                return lookup[alias.lower()]
        return None

    company_col = pick("company") or raw.columns[0]
    out = pd.DataFrame()
    out["company"] = raw[company_col].astype(str).str.strip()
    out = out[(out["company"] != "") & (out["company"].str.lower() != "nan")]
    for target in ["category", "country", "state", "city", "home_base", "website", "notes", "lat", "lon"]:
        col = pick(target)
        out[target] = raw.loc[out.index, col] if col else ""
    out["category"] = out["category"].replace("", "Uploaded Lead").fillna("Uploaded Lead")
    out["type"] = out["category"]
    out["source"] = "Uploaded Excel"
    out["state"] = out.apply(
        lambda r: str(r["state"]).strip().upper() if str(r["state"]).strip() else infer_region_from_text(f'{r["home_base"]} {r["city"]}'),
        axis=1,
    )
    out["country"] = out.apply(
        lambda r: str(r["country"]).strip() if str(r["country"]).strip() else infer_country_from_region(r["state"]),
        axis=1,
    )
    out["sales"] = 0.0
    out["priority"] = "Lead"
    out["lat"] = pd.to_numeric(out["lat"], errors="coerce")
    out["lon"] = pd.to_numeric(out["lon"], errors="coerce")
    return out[["source", "company", "category", "type", "country", "state", "city", "home_base", "website", "notes", "sales", "priority", "lat", "lon"]]

def get_uploaded_account_df():
    rows = st.session_state.get("account_map_rows", [])
    if not rows:
        return pd.DataFrame(columns=["source", "company", "category", "type", "country", "state", "city", "home_base", "website", "notes", "sales", "priority", "lat", "lon"])
    df = pd.DataFrame(rows)
    for col in ["lat", "lon", "sales"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    return df

def get_google_places_account_df():
    rows = st.session_state.get("google_places_rows", [])
    if not rows:
        return pd.DataFrame(columns=["source", "company", "category", "type", "country", "state", "city", "home_base", "website", "notes", "sales", "priority", "lat", "lon"])
    df = pd.DataFrame(rows)
    for col in ["lat", "lon", "sales"]:
        df[col] = pd.to_numeric(df.get(col), errors="coerce")
    return df

def google_places_text_search(api_key_value, text_query, category_label, max_results=10, include_contact_fields=False):
    if not api_key_value:
        raise ValueError("GOOGLE_PLACES_API_KEY가 설정되어 있지 않습니다.")
    endpoint = "https://places.googleapis.com/v1/places:searchText"
    fields = [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.primaryType",
        "places.googleMapsUri",
        "places.businessStatus",
    ]
    if include_contact_fields:
        fields.extend([
            "places.websiteUri",
            "places.nationalPhoneNumber",
            "places.rating",
            "places.userRatingCount",
        ])
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key_value,
        "X-Goog-FieldMask": ",".join(fields),
    }
    payload = {
        "textQuery": text_query,
        "languageCode": "en",
        "maxResultCount": int(max(1, min(max_results, 20))),
    }
    response = requests.post(endpoint, headers=headers, json=payload, timeout=20)
    if response.status_code >= 400:
        detail = response.text[:500]
        raise ValueError(f"Google Places 요청 실패 ({response.status_code}): {detail}")
    places = response.json().get("places", [])
    rows = []
    for place in places:
        display = place.get("displayName", {}) or {}
        location = place.get("location", {}) or {}
        address = place.get("formattedAddress", "") or ""
        region = infer_region_from_text(address)
        country = infer_country_from_region(region)
        if country == "Unknown":
            if "canada" in address.lower():
                country = "Canada"
            elif "usa" in address.lower() or "united states" in address.lower():
                country = "United States"
        contact_notes = []
        if place.get("businessStatus"):
            contact_notes.append(place.get("businessStatus"))
        if include_contact_fields and place.get("nationalPhoneNumber"):
            contact_notes.append(place.get("nationalPhoneNumber"))
        if include_contact_fields and place.get("rating"):
            contact_notes.append(f'Rating {place.get("rating")} ({place.get("userRatingCount", 0):,})')
        rows.append({
            "source": "Google Places",
            "company": display.get("text", "Unknown"),
            "category": category_label or "Google Places Lead",
            "type": place.get("primaryType", "Place"),
            "country": country,
            "state": region,
            "city": "",
            "home_base": address,
            "website": place.get("websiteUri") or place.get("googleMapsUri", ""),
            "notes": " · ".join(contact_notes) if contact_notes else "Google Places search result",
            "sales": 0.0,
            "priority": "Lead",
            "lat": location.get("latitude"),
            "lon": location.get("longitude"),
        })
    return pd.DataFrame(rows)

def build_account_map_df(market_df, competitor_detail_df=None):
    frames = []
    if market_df is not None and not market_df.empty:
        m = market_df.copy()
        m["sales_base"] = m["sales_2025"].fillna(m["sales_2024"]).fillna(m["sales_2023"]).fillna(m["sales_2022"]).fillna(0)
        if "opportunity_score" not in m.columns:
            m = add_opportunity_scores(m)
        frames.append(pd.DataFrame({
            "source": "Market Insight",
            "company": m["company"],
            "category": m["category"],
            "type": m["type"],
            "country": "United States",
            "state": m["state"].astype(str).str.upper(),
            "city": m["home_base"].astype(str).str.replace(r",\s*[A-Z]{2}$", "", regex=True),
            "home_base": m["home_base"],
            "website": "",
            "notes": m["category"],
            "sales": m["sales_base"],
            "priority": m["grade"],
            "lat": pd.NA,
            "lon": pd.NA,
        }))
    if competitor_detail_df is not None and not competitor_detail_df.empty:
        d = competitor_detail_df.copy()
        d["state"] = d["destination"].map(infer_region_from_text)
        d = d[d["state"].isin(REGION_CENTERS.keys())]
        if not d.empty:
            imp = (
                d.groupby(["importer", "country", "state"], as_index=False)
                .agg(
                    weight_kg=("weight_kg", "sum"),
                    competitors=("competitor", lambda s: ", ".join(sorted(set(map(str, s)))[:4])),
                    destination=("destination", lambda s: ", ".join(pd.Series(s).astype(str).dropna().unique()[:3])),
                )
            )
            frames.append(pd.DataFrame({
                "source": "ImportYeti Upload",
                "company": imp["importer"],
                "category": "ImportYeti Lead",
                "type": "Importer",
                "country": imp["country"].where(imp["country"].astype(str).str.len() > 0, imp["state"].map(infer_country_from_region)),
                "state": imp["state"],
                "city": imp["destination"],
                "home_base": imp["destination"],
                "website": "",
                "notes": "경쟁사 흔적: " + imp["competitors"],
                "sales": imp["weight_kg"],
                "priority": "Lead",
                "lat": pd.NA,
                "lon": pd.NA,
            }))
    uploaded = get_uploaded_account_df()
    if not uploaded.empty:
        frames.append(uploaded)
    google_places = get_google_places_account_df()
    if not google_places.empty:
        frames.append(google_places)
    if not frames:
        return pd.DataFrame(columns=["source", "company", "category", "type", "country", "state", "city", "home_base", "website", "notes", "sales", "priority", "lat", "lon"])

    df = pd.concat(frames, ignore_index=True)
    df["company"] = df["company"].astype(str).str.strip()
    df = df[(df["company"] != "") & (df["company"].str.lower() != "nan")]
    df["state"] = df["state"].astype(str).str.upper().replace({"NAN": "", "NONE": ""})
    df["country"] = df.apply(lambda r: r["country"] if str(r["country"]).strip() and str(r["country"]).lower() != "nan" else infer_country_from_region(r["state"]), axis=1)
    df["sales"] = pd.to_numeric(df["sales"], errors="coerce").fillna(0)
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    for idx, row in df.iterrows():
        if pd.isna(row["lat"]) or pd.isna(row["lon"]):
            center = REGION_CENTERS.get(row["state"])
            if center:
                lat_offset, lon_offset = account_jitter(row["company"], row["state"], idx)
                df.at[idx, "lat"] = center[0] + lat_offset
                df.at[idx, "lon"] = center[1] + lon_offset
    df = df.drop_duplicates(subset=["company", "state", "source"], keep="first")
    return df.reset_index(drop=True)

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

def build_alerts(usd_krw, v_wti, d_wti, v_mortgage, v_scfi, d_scfi, d_pvc, d_dotp):
    rules = [
        ("critical" if usd_krw >= 1600 else "warn" if usd_krw >= 1550 else "watch" if usd_krw >= 1500 else None,
         "USD/KRW", f"{usd_krw:,.0f}원", "환율 고점 구간입니다. 견적 유효기간과 원화 환산 마진을 같이 점검하세요."),
        ("critical" if v_wti >= 90 else "warn" if v_wti >= 85 else "watch" if d_wti >= 5 else None,
         "WTI", f"${v_wti:,.1f}", "유가 상승은 PVC, 운임, 에너지성 비용으로 전이될 수 있습니다."),
        ("critical" if v_mortgage >= 7.0 else "warn" if v_mortgage >= 6.5 else None,
         "30Y Mortgage", f"{v_mortgage:.2f}%", "모기지 금리 부담이 주택 거래와 리모델링 심리에 영향을 줄 수 있습니다."),
        ("critical" if v_scfi >= 3200 else "warn" if v_scfi >= 3000 else "watch" if d_scfi >= 10 else None,
         "SCFI", f"{v_scfi:,.0f}", "운임 지수가 높은 구간입니다. 선적 일정과 견적 운임 가정을 재확인하세요."),
        ("warn" if d_pvc >= 10 else "watch" if d_pvc >= 5 else None,
         "PVC", f"{d_pvc:+.1f}% MoM", "PVC 구매 지수 상승폭이 커지고 있습니다. 원가 반영 타이밍을 확인하세요."),
        ("warn" if d_dotp >= 10 else "watch" if d_dotp >= 5 else None,
         "DOTP", f"{d_dotp:+.1f}% MoM", "DOTP 구매 지수 상승폭이 커지고 있습니다. 단가 민감도를 점검하세요."),
    ]
    alerts = []
    for level, title, value, message in rules:
        if level:
            alerts.append({"level": level, "title": title, "value": value, "message": message})
    return alerts

def render_alert_cards(alerts):
    if not alerts:
        return (
            '<div class="alert-grid">'
            '<div class="alert-card alert-watch"><div class="alert-level">NORMAL</div>'
            '<div class="alert-title">주의 임계값 초과 없음</div>'
            '<div class="alert-msg">현재 설정된 환율, 유가, 운임, 주택금리, 원재료 기준에서 즉시 경고 항목은 없습니다.</div></div>'
            '</div>'
        )
    label = {"critical": "CRITICAL", "warn": "WARNING", "watch": "WATCH"}
    cards = ""
    for a in alerts[:6]:
        cards += (
            f'<div class="alert-card alert-{a["level"]}">'
            f'<div class="alert-level">{label.get(a["level"], "WATCH")}</div>'
            f'<div class="alert-title">{html.escape(a["title"])} · {html.escape(a["value"])}</div>'
            f'<div class="alert-msg">{html.escape(a["message"])}</div>'
            '</div>'
        )
    return f'<div class="alert-grid">{cards}</div>'

def build_weekly_brief(summary, alerts, d_fx, d_scfi, d_pvc, d_dotp):
    top_alert = alerts[0]["title"] if alerts else "주요 임계값 초과 없음"
    return [
        f"이번 주 우선 체크 항목은 {top_alert}입니다.",
        summary["demand"],
        summary["rate"],
        f"환율은 20거래일 기준 {d_fx:+.1f}% 흐름이며, 운임은 4주 기준 SCFI {d_scfi:+.1f}%입니다.",
        f"구매팀 지수는 PVC {d_pvc:+.1f}% MoM, DOTP {d_dotp:+.1f}% MoM으로 원가 반영 여부를 확인해야 합니다.",
    ]

def last_valid_date(df, col=None, fmt="%Y-%m-%d"):
    if df is None or df.empty or "date" not in df.columns:
        return "N/A"
    clean = df.copy()
    if col and col in clean.columns:
        clean = clean[clean[col].notna()]
    clean = clean.dropna(subset=["date"])
    if clean.empty:
        return "N/A"
    return pd.Timestamp(clean["date"].max()).strftime(fmt)

def build_update_rows():
    return pd.DataFrame([
        {"데이터": "FRED Housing / Macro", "출처": "FRED API", "최근 기준": max(last_valid_date(df_housing, "주택착공"), last_valid_date(df_cpi, "CPI")), "업데이트": "자동"},
        {"데이터": "USD/KRW", "출처": "Exchange API + FRED", "최근 기준": datetime.now().strftime("%Y-%m-%d %H:%M"), "업데이트": "자동"},
        {"데이터": "PVC / DOTP", "출처": "구매팀 수기 지수", "최근 기준": last_valid_date(df_purchase, fmt="%Y-%m"), "업데이트": "수기/엑셀"},
        {"데이터": "SCFI / CCFI", "출처": "국가물류통합정보센터", "최근 기준": last_valid_date(df_freight, "SCFI"), "업데이트": "엑셀 반영"},
        {"데이터": "Market Insight", "출처": "내부 조사 자료", "최근 기준": "2026-06-19", "업데이트": "수기"},
        {"데이터": "Tariff Brief", "출처": "내부 보고 자료", "최근 기준": "2026-06-19", "업데이트": "수기"},
    ])

def normalize_purchase_upload(uploaded):
    df = pd.read_excel(uploaded)
    df.columns = [str(c).strip() for c in df.columns]
    month_col = "월" if "월" in df.columns else "Month" if "Month" in df.columns else df.columns[0]
    rename = {month_col: "월"}
    for c in df.columns:
        up = str(c).upper()
        if up == "PVC":
            rename[c] = "PVC"
        elif up == "DOTP":
            rename[c] = "DOTP"
    out = df.rename(columns=rename)
    needed = ["월", "PVC", "DOTP"]
    if not all(c in out.columns for c in needed):
        raise ValueError("월, PVC, DOTP 컬럼이 필요합니다.")
    return out[needed]

def set_freight_index_df(df):
    clean = df.copy()
    clean.columns = [str(c).strip() for c in clean.columns]
    first_col = clean.columns[0] if len(clean.columns) else None
    if first_col is not None:
        first_values = clean[first_col].astype(str).str.upper()
        if first_values.str.contains("SCFI|CCFI", regex=True).any():
            records = []
            for _, row in clean.iterrows():
                label = str(row[first_col]).upper()
                if "SCFI" not in label and "CCFI" not in label:
                    continue
                index_name = "SCFI" if "SCFI" in label else "CCFI"
                for c in clean.columns[1:]:
                    dt = pd.to_datetime(str(c), errors="coerce")
                    if pd.isna(dt):
                        continue
                    records.append({"date": dt, index_name: row[c]})
            if records:
                clean = pd.DataFrame(records).groupby("date", as_index=False).first()
                clean.columns = [str(c).strip() for c in clean.columns]
    rename = {}
    for c in clean.columns:
        up = str(c).upper()
        if c in ["기준일", "날짜", "DATE"] or up == "DATE":
            rename[c] = "date"
        elif "SCFI" in up:
            rename[c] = "SCFI"
        elif "CCFI" in up:
            rename[c] = "CCFI"
    clean = clean.rename(columns=rename)
    if "date" not in clean.columns or not {"SCFI", "CCFI"}.intersection(clean.columns):
        raise ValueError("date/기준일과 SCFI 또는 CCFI 컬럼이 필요합니다.")
    for col in ["SCFI", "CCFI"]:
        if col not in clean.columns:
            clean[col] = None
        clean[col] = pd.to_numeric(clean[col], errors="coerce")
    clean["date"] = pd.to_datetime(clean["date"], errors="coerce")
    clean = clean.dropna(subset=["date"]).sort_values("date")
    st.session_state.freight_index_rows = clean[["date", "SCFI", "CCFI"]].assign(
        date=lambda x: x["date"].dt.strftime("%Y-%m-%d")
    ).to_dict("records")

def add_opportunity_scores(df):
    scored = df.copy()
    sales_col = "sales_2025" if scored["sales_2025"].notna().any() else "sales_2024"
    scored["sales_base"] = scored[sales_col].fillna(scored["sales_2024"]).fillna(scored["sales_2023"]).fillna(0)
    max_sales = scored["sales_base"].max() or 1
    scored["sales_score"] = scored["sales_base"].clip(lower=0) / max_sales * 45
    rank_base = scored["rank_2025"].fillna(scored["rank_2024"]).fillna(50)
    scored["rank_score"] = ((55 - rank_base).clip(lower=0, upper=55) / 55) * 25
    state_counts = scored.groupby("state")["company"].transform("count")
    max_state = state_counts.max() or 1
    scored["state_score"] = state_counts / max_state * 15
    growth = ((scored["sales_2025"] - scored["sales_2024"]) / scored["sales_2024"] * 100).replace([float("inf"), -float("inf")], 0).fillna(0)
    scored["growth_score"] = growth.clip(lower=0, upper=25) / 25 * 10
    scored["category_score"] = scored["category"].map({"Rising Stars": 5, "Top Distributors": 4, "Top Retailers": 3}).fillna(2)
    scored["opportunity_score"] = (scored["sales_score"] + scored["rank_score"] + scored["state_score"] + scored["growth_score"] + scored["category_score"]).clip(upper=100).round(1)
    scored["grade"] = pd.cut(scored["opportunity_score"], bins=[-1, 54.9, 74.9, 100], labels=["C", "B", "A"]).astype(str)
    return scored

def build_action_recommendations(alerts, usd_krw, v_scfi, d_scfi, v_mortgage, d_pvc, d_dotp):
    recs = []
    alert_titles = {a["title"] for a in alerts}
    if "SCFI" in alert_titles or v_scfi >= 2800 or d_scfi >= 8:
        recs.append({"영역": "운임", "권고 액션": "신규 견적의 운임 유효기간을 7~10일로 짧게 관리하고, 선적 예정 건은 선복 확보 여부를 먼저 확인"})
    if "USD/KRW" in alert_titles or usd_krw >= 1500:
        recs.append({"영역": "환율", "권고 액션": "원화 환산 매출은 우호적이나 달러 비용 항목과 가격 통보 시점을 함께 점검"})
    if v_mortgage >= 6.5:
        recs.append({"영역": "수요", "권고 액션": "주택/리모델링 수요 민감 거래선은 보수적 판매계획과 프로모션 제품 믹스 재점검"})
    if d_pvc >= 5 or d_dotp >= 5:
        recs.append({"영역": "원가", "권고 액션": "PVC/DOTP 상승분이 견적 원가에 반영되는지 확인하고, 월별 구매팀 지수 업데이트 주기를 고정"})
    if not recs:
        recs.append({"영역": "운영", "권고 액션": "즉시 조정이 필요한 위험 신호는 낮습니다. 기존 견적·선적·가격 정책을 유지하면서 주간 모니터링"})
    recs.append({"영역": "보고", "권고 액션": "상부 보고 시 Alert, 운임/환율, 원자재, 주요 뉴스 3개를 한 페이지로 요약"})
    return pd.DataFrame(recs[:5])

def build_watchlist_items():
    return {
        "USD/KRW": {"value": f"{usd_krw:,.0f}", "change": f"20거래일 {d_fx:+.1f}%"},
        "SCFI": {"value": f"{v_scfi:,.0f}", "change": f"4주 {d_scfi:+.1f}%"},
        "PVC": {"value": f"{v_pvc:,.2f}", "change": f"MoM {d_pvc:+.1f}%"},
        "DOTP": {"value": f"{v_dotp:,.2f}", "change": f"MoM {d_dotp:+.1f}%"},
        "WTI": {"value": f"${v_wti:.1f}", "change": f"{d_wti:+.1f}%"},
        "30Y Mortgage": {"value": f"{v_mortgage:.2f}%", "change": f"{d_mortgage:+.2f}%p"},
        "Housing Starts": {"value": f"{v_housing:,.0f}K", "change": f"MoM {d_housing:+.1f}%"},
        "Tariff": {"value": f"{st.session_state.sim_duty:.0f}%", "change": "임시 관세"},
    }

def render_watchlist(selected):
    items = build_watchlist_items()
    cards = ""
    for name in selected:
        item = items.get(name)
        if not item:
            continue
        cards += (
            f'<div class="watch-card"><div class="watch-k">{html.escape(name)}</div>'
            f'<div class="watch-v">{html.escape(item["value"])}</div>'
            f'<div class="watch-c">{html.escape(item["change"])}</div></div>'
        )
    return f'<div class="watch-grid">{cards}</div>' if cards else ""

def get_comment_log_df():
    if "monthly_comment_log" not in st.session_state:
        st.session_state.monthly_comment_log = []
    return pd.DataFrame(st.session_state.monthly_comment_log)

def save_monthly_comment(month, category, comment):
    if "monthly_comment_log" not in st.session_state:
        st.session_state.monthly_comment_log = []
    rows = [r for r in st.session_state.monthly_comment_log if not (r["월"] == month and r["카테고리"] == category)]
    rows.append({
        "월": month,
        "카테고리": category,
        "코멘트": comment.strip(),
        "작성/수정": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    st.session_state.monthly_comment_log = sorted(rows, key=lambda r: (r["월"], r["카테고리"]), reverse=True)

def build_customer_impact(market_view, state_summary, alerts):
    if market_view.empty or state_summary.empty:
        return pd.DataFrame()
    alert_names = {a["title"] for a in alerts}
    state_priority = (
        market_view.groupby("state", as_index=False)
        .agg(
            priority_a=("grade", lambda s: int((s == "A").sum())),
            avg_score=("opportunity_score", "mean"),
            top_accounts=("company", lambda s: ", ".join(s.head(3))),
        )
    )
    impact = state_summary.merge(state_priority, on="state", how="left").fillna({"priority_a": 0, "avg_score": 0, "top_accounts": ""})
    risk_score = 0
    if "SCFI" in alert_names or d_scfi >= 8:
        risk_score += 25
    if "USD/KRW" in alert_names:
        risk_score += 15
    if "30Y Mortgage" in alert_names or v_mortgage >= 6.5:
        risk_score += 15
    if "PVC" in alert_names or "DOTP" in alert_names:
        risk_score += 10
    impact["impact_score"] = (
        impact["companies"].rank(pct=True) * 30
        + impact["avg_score"].fillna(0) * 0.45
        + impact["priority_a"].fillna(0) * 7
        + risk_score
    ).clip(upper=100).round(1)
    impact["영향도"] = pd.cut(impact["impact_score"], bins=[-1, 54.9, 74.9, 100], labels=["LOW", "MID", "HIGH"]).astype(str)
    impact["영업 포인트"] = impact.apply(
        lambda r: "운임/환율 변동 반영 견적 관리 우선" if r["영향도"] == "HIGH"
        else "주요 거래선 모니터링 및 분기별 업데이트" if r["영향도"] == "MID"
        else "일반 모니터링",
        axis=1,
    )
    return impact.sort_values("impact_score", ascending=False)

DESIGN_KEYWORDS = {
    "warm wood": ["warm wood", "warm oak", "natural oak", "blonde oak", "oak visuals", "soft oak"],
    "wide plank": ["wide plank", "longer plank", "long plank", "plank"],
    "matte finish": ["matte", "low gloss", "soft finish"],
    "stone look": ["stone", "marble", "travertine", "slate", "mineral"],
    "commercial neutral": ["commercial", "neutral", "greige", "beige", "taupe"],
    "biophilic": ["biophilic", "nature", "natural", "organic"],
    "sustainable": ["sustainable", "sustainability", "recycled", "responsible"],
    "rigid core": ["rigid", "rigid core", "spc", "wpc"],
    "performance": ["performance", "durable", "scratch", "waterproof"],
    "texture": ["texture", "embossed", "realistic", "grain"],
}

DESIGN_TAXONOMY = {
    "Material": {
        "Wood": ["wood", "oak", "walnut", "maple", "plank"],
        "Stone": ["stone", "marble", "slate", "travertine", "mineral"],
        "Concrete": ["concrete", "cement", "industrial"],
        "Textile": ["textile", "woven", "fabric"],
        "Ceramic": ["ceramic", "tile", "porcelain"],
    },
    "Color": {
        "Warm Neutral": ["warm", "beige", "taupe", "honey", "natural"],
        "Greige": ["greige", "gray", "grey"],
        "Light Oak": ["blonde", "light", "white oak"],
        "Dark Walnut": ["dark", "walnut", "espresso"],
        "Soft Beige": ["soft", "cream", "sand"],
    },
    "Pattern": {
        "Wide Plank": ["wide plank", "long plank", "plank"],
        "Herringbone": ["herringbone", "chevron"],
        "Mixed Width": ["mixed width", "multi width"],
        "Mineral": ["mineral", "terrazzo", "aggregate"],
        "Realistic Texture": ["texture", "embossed", "grain", "realistic"],
    },
}

def collect_design_articles(limit=18, source_mode="FCW + FCNews"):
    fcw_categories = ["Style & Design", "Products", "Features", "Sustainability"]
    fcnews_categories = ["Resilient", "Wood", "Tile", "Carpet", "Technology", "Laminate"]
    rows = []
    seen = set()
    if source_mode in ["FCW + FCNews", "FCW only"]:
        for cat in fcw_categories:
            for item in llm.fetch_fcw_news(cat, limit=8):
                link = item.get("link", "")
                title = item.get("title", "")
                if not link or link in seen or not title:
                    continue
                item = dict(item)
                item["design_source_category"] = cat
                item["source_group"] = "FCW"
                rows.append(item)
                seen.add(link)
                if len(rows) >= limit and source_mode == "FCW only":
                    return rows
    if source_mode in ["FCW + FCNews", "FCNews only"]:
        for cat in fcnews_categories:
            for item in llm.fetch_fcnews_news(cat, limit=8):
                link = item.get("link", "")
                title = item.get("title", "")
                if not link or link in seen or not title:
                    continue
                item = dict(item)
                item["design_source_category"] = cat
                item["source_group"] = "FCNews"
                rows.append(item)
                seen.add(link)
                if len(rows) >= limit and source_mode == "FCNews only":
                    return rows
    return rows[:limit]

def build_source_keyword_comparison(items):
    rows = []
    for source in ["FCW", "FCNews"]:
        sub = [i for i in items if i.get("source_group") == source]
        if not sub:
            continue
        kdf = extract_design_keywords(sub)
        for _, r in kdf.head(6).iterrows():
            rows.append({"Source": source, "Keyword": r["Keyword"], "Mentions": r["Mentions"]})
    return pd.DataFrame(rows)

def collect_fcnews_guides():
    guides = [
        {"자료": "FCNews Home", "내용": "Floor Covering News 최신 기사", "링크": "https://www.fcnews.net/"},
        {"자료": "Resilient", "내용": "LVT/SPC 포함 resilient 카테고리", "링크": "https://www.fcnews.net/category/news/resilient/"},
        {"자료": "Wood", "내용": "우드 디자인/수종/컬러 트렌드", "링크": "https://www.fcnews.net/category/news/wood/"},
        {"자료": "Tile", "내용": "스톤/타일 룩 디자인 레퍼런스", "링크": "https://www.fcnews.net/category/news/tile/"},
        {"자료": "Technology", "내용": "디지털 프린팅/EIR/시각화 기술", "링크": "https://www.fcnews.net/category/news/technology/"},
        {"자료": "LVT Selling Guide 2026", "내용": "FCNews supplement / guide watch", "링크": "https://www.fcnews.net/"},
    ]
    return pd.DataFrame(guides)

def design_text_blob(items):
    return " ".join([f"{i.get('title','')} {i.get('summary','')}" for i in items]).lower()

def extract_design_keywords(items):
    blob = design_text_blob(items)
    rows = []
    for key, terms in DESIGN_KEYWORDS.items():
        count = sum(blob.count(term) for term in terms)
        if count:
            rows.append({"Keyword": key, "Mentions": count})
    if not rows:
        rows = [
            {"Keyword": "warm wood", "Mentions": 1},
            {"Keyword": "wide plank", "Mentions": 1},
            {"Keyword": "matte finish", "Mentions": 1},
            {"Keyword": "commercial neutral", "Mentions": 1},
            {"Keyword": "performance", "Mentions": 1},
        ]
    return pd.DataFrame(rows).sort_values("Mentions", ascending=False).reset_index(drop=True)

def build_design_taxonomy(items):
    blob = design_text_blob(items)
    rows = []
    for axis, groups in DESIGN_TAXONOMY.items():
        for name, terms in groups.items():
            score = sum(blob.count(t) for t in terms)
            rows.append({"Axis": axis, "Trend Bucket": name, "Signal": score})
    df = pd.DataFrame(rows)
    return df.sort_values(["Axis", "Signal"], ascending=[True, False])

def build_product_implications(keyword_df):
    implication_map = {
        "warm wood": "주거용 LVT 우드 패턴에서 warm oak / natural oak 컬러웨이 보강 검토",
        "wide plank": "롱/와이드 플랭크 규격과 샘플 보드 연출 강화",
        "matte finish": "저광택 표면, 리얼 텍스처, 무광 촉감 표현 샘플 우선 검토",
        "stone look": "상업용/호스피탈리티용 스톤·미네랄 룩 패턴 레퍼런스 확보",
        "commercial neutral": "오피스·리테일 채널용 저채도 greige/taupe 팔레트 검토",
        "biophilic": "자연 소재감, 부드러운 우드 그레인, 실내 웰빙 메시지와 연결",
        "sustainable": "친환경/재활용/책임소재 메시지를 제품 스토리와 연결",
        "rigid core": "SPC/rigid core 제품의 디자인 완성도와 성능 메시지 동시 강화",
        "performance": "내구성, 방수, 유지관리 장점을 디자인 설명과 함께 제안",
        "texture": "EIR/embossing 표현과 실제 목재 질감 차별화 포인트 정리",
    }
    rows = []
    for _, r in keyword_df.head(8).iterrows():
        key = r["Keyword"]
        rows.append({
            "Trend": key,
            "Signal": int(r["Mentions"]),
            "Product Implication": implication_map.get(key, "제품 컬러/패턴/표면감 레퍼런스 후보로 검토"),
        })
    return pd.DataFrame(rows)

def render_trend_pills(keyword_df):
    pills = ""
    for _, r in keyword_df.head(10).iterrows():
        pills += f'<span class="trend-pill">{html.escape(str(r["Keyword"]))}<span class="trend-count">{int(r["Mentions"])}</span></span>'
    return f'<div class="trend-pill-wrap">{pills}</div>'

def render_moodboard(items):
    cards = ""
    for item in items[:8]:
        title = html.escape(item.get("title", "Design Reference"))
        link = html.escape(item.get("link", ""))
        image = html.escape(item.get("image", "") or "")
        media = f'<img src="{image}" alt="{title}" loading="lazy"/>' if image else '<div class="mood-fallback">DESIGN<br>REFERENCE</div>'
        cards += (
            f'<a class="mood-card" href="{link}" target="_blank" rel="noopener noreferrer">'
            f'{media}<div class="mood-overlay">{title}</div></a>'
        )
    return f'<div class="mood-grid">{cards}</div>'

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

def create_client_brief_pdf(ctx):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=13*mm, leftMargin=13*mm,
        topMargin=11*mm, bottomMargin=10*mm
    )
    styles = getSampleStyleSheet()
    navy = colors.HexColor("#0E2372")
    gold = colors.HexColor("#E8B339")
    ink = colors.HexColor("#172033")
    muted = colors.HexColor("#657186")
    line = colors.HexColor("#D9E1EE")
    pale = colors.HexColor("#F5F7FB")

    title = ParagraphStyle("ClientTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=16, leading=18, textColor=colors.white, alignment=0)
    sub = ParagraphStyle("ClientSub", parent=styles["Normal"], fontName="Helvetica", fontSize=7.8, leading=10, textColor=colors.HexColor("#DCE5FF"), alignment=2)
    h = ParagraphStyle("ClientHead", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10.2, leading=13, textColor=navy, spaceBefore=4, spaceAfter=4)
    body = ParagraphStyle("ClientBody", parent=styles["BodyText"], fontName="Helvetica", fontSize=8.7, leading=12.2, textColor=ink)
    small = ParagraphStyle("ClientSmall", parent=body, fontSize=7.5, leading=10.4, textColor=muted)
    card_label = ParagraphStyle("CardLabel", parent=small, fontName="Helvetica-Bold", fontSize=6.8, leading=8, textColor=muted)
    card_value = ParagraphStyle("CardValue", parent=body, fontName="Helvetica-Bold", fontSize=14, leading=16, textColor=ink)
    card_note = ParagraphStyle("CardNote", parent=small, fontSize=6.9, leading=8.4, textColor=muted)
    callout = ParagraphStyle("Callout", parent=body, fontName="Helvetica-Bold", fontSize=10, leading=14, textColor=colors.white)

    def esc(value):
        return html.escape(str(value))

    def num(value, fmt, default="N/A"):
        try:
            if value is None or pd.isna(value):
                return default
            return fmt.format(value)
        except Exception:
            return default

    def bullet(text):
        return Paragraph(f"- {esc(text)}", body)

    logo_path = os.path.join(os.path.dirname(__file__), "logo_white_t.png")
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=36*mm, height=10*mm)
    else:
        logo = Paragraph("KCC GLASS", ParagraphStyle("LogoText", parent=title, fontSize=12, leading=14))

    report_date = datetime.now().strftime("%B %d, %Y")
    header = Table(
        [[logo, Paragraph("U.S. LVT MARKET INDICATOR BRIEF", title), Paragraph(f"Reference only<br/>{report_date}", sub)]],
        colWidths=[42*mm, 91*mm, 48*mm],
        rowHeights=[18*mm],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), navy),
        ("LINEBELOW", (0, 0), (-1, -1), 1.6, gold),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))

    mortgage = ctx.get("mortgage")
    scfi_chg = ctx.get("d_scfi")
    fx_chg = ctx.get("d_fx")
    wti_chg = ctx.get("d_wti")
    pvc_chg = ctx.get("d_pvc")
    dotp_chg = ctx.get("d_dotp")

    headline = "U.S. flooring demand remains rate-sensitive; FX, freight and raw-material signals should be checked before quote finalization."
    if scfi_chg is not None and scfi_chg >= 8:
        headline = "Freight cost pressure is rising; quote validity, shipment timing and logistics assumptions should be reviewed carefully."
    elif fx_chg is not None and abs(fx_chg) >= 2:
        headline = "FX volatility is elevated; KRW/USD conversion assumptions should be checked before customer communication."
    elif mortgage is not None and mortgage >= 6.5:
        headline = "High mortgage rates continue to weigh on U.S. housing sentiment, keeping demand visibility selective."

    callout_table = Table([[Paragraph(headline, callout)]], colWidths=[181*mm])
    callout_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#172033")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#172033")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    metric_cards = [
        ("USD/KRW", num(ctx.get("usd_krw"), "{:,.0f}"), num(fx_chg, "20D {:+.1f}%"), "FX reference"),
        ("30Y Mortgage", num(mortgage, "{:.2f}%"), num(ctx.get("d_mortgage"), "{:+.2f}ppt"), "Demand sentiment"),
        ("SCFI", num(ctx.get("scfi"), "{:,.0f}"), num(scfi_chg, "4W {:+.1f}%"), "Freight index"),
        ("WTI", num(ctx.get("wti"), "${:.1f}"), num(wti_chg, "{:+.1f}%"), "Oil and resin signal"),
        ("CPI", num(ctx.get("cpi"), "{:.1f}"), num(ctx.get("d_cpi"), "{:+.1f}%"), "Inflation backdrop"),
    ]
    card_cells = []
    for label, value, change, note in metric_cards:
        card_cells.append([
            Paragraph(label, card_label),
            Paragraph(value, card_value),
            Paragraph(change, card_note),
            Paragraph(note, card_note),
        ])
    metrics_table = Table([card_cells], colWidths=[36.2*mm]*5)
    metrics_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), pale),
        ("BOX", (0, 0), (-1, -1), 0.4, line),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    market_read = [
        f"USD/KRW is at {num(ctx.get('usd_krw'), '{:,.0f}')}, with a {num(fx_chg, '{:+.1f}%')} move over the last 20 trading days.",
        f"The 30Y mortgage rate is {num(mortgage, '{:.2f}%')}, keeping U.S. housing demand sensitive to financing conditions.",
        f"SCFI is {num(ctx.get('scfi'), '{:,.0f}')}, showing {num(scfi_chg, '{:+.1f}%')} over the last four weeks.",
        f"WTI is {num(ctx.get('wti'), '${:.1f}')}; PVC/DOTP purchase indices show {num(pvc_chg, '{:+.1f}%')} / {num(dotp_chg, '{:+.1f}%')} MoM.",
    ]
    implications = [
        "Use FX and freight volatility as context when discussing quote validity periods.",
        "Treat rate and housing indicators as demand-sentiment references, not as a formal demand forecast.",
        "Confirm product specification, delivery timing and commercial terms case by case.",
        "This brief is intended as a market reference for customer discussion and internal alignment.",
    ]
    two_col = Table(
        [[
            [Paragraph("Market Read", h)] + [bullet(x) for x in market_read],
            [Paragraph("Commercial Implication", h)] + [bullet(x) for x in implications],
        ]],
        colWidths=[88*mm, 88*mm],
    )
    two_col.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.4, line),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, line),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    source_rows = [
        ["Indicator", "Current", "Change / Note", "Business Use"],
        ["Housing Starts", num(ctx.get("housing"), "{:,.0f}K"), num(ctx.get("d_housing"), "{:+.1f}% MoM"), "U.S. residential demand pulse"],
        ["New Home Sales", num(ctx.get("newsales"), "{:,.0f}K"), "Monthly release", "Flooring replacement/new-build context"],
        ["SCFI / CCFI", f"{num(ctx.get('scfi'), '{:,.0f}')} / {num(ctx.get('ccfi'), '{:,.0f}')}", f"{num(scfi_chg, '{:+.1f}%')} / {num(ctx.get('d_ccfi'), '{:+.1f}%')} 4W", "Ocean freight pressure"],
        ["PVC / DOTP", f"{num(ctx.get('pvc'), '{:,.2f}')} / {num(ctx.get('dotp'), '{:,.2f}')}", f"{num(pvc_chg, '{:+.1f}%')} / {num(dotp_chg, '{:+.1f}%')} MoM", "Raw material cost reference"],
    ]
    source_table = Table(source_rows, colWidths=[35*mm, 39*mm, 45*mm, 62*mm], repeatRows=1)
    source_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("BACKGROUND", (0, 0), (-1, 0), navy),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, 0), 7.3),
        ("FONTSIZE", (0, 1), (-1, -1), 7.1),
        ("TEXTCOLOR", (0, 1), (-1, -1), ink),
        ("GRID", (0, 0), (-1, -1), 0.35, line),
        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    footer = Paragraph(
        "Disclaimer: This document is a market-reference brief prepared from public indicators and internal monitoring data. "
        "It is not a price quotation, contract term, market forecast or investment advice. Product specifications, pricing and delivery terms should be confirmed separately.",
        small,
    )

    story = [
        header,
        Spacer(1, 8),
        callout_table,
        Spacer(1, 8),
        metrics_table,
        Spacer(1, 8),
        two_col,
        Spacer(1, 8),
        Paragraph("Indicator Detail", h),
        source_table,
        Spacer(1, 8),
        HRFlowable(width="100%", thickness=.4, color=line),
        Spacer(1, 5),
        footer,
    ]
    doc.build(story)
    buffer.seek(0)
    return buffer

def create_monthly_pdf_report(metrics, summary, action_recs, alerts, freight_rows,
                              raw_rows, keyword_df, implication_df, comment_df=None):
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    buffer = BytesIO()
    pdfmetrics.registerFont(UnicodeCIDFont("HYGothic-Medium"))
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=13*mm, leftMargin=13*mm,
        topMargin=12*mm, bottomMargin=12*mm
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle("MTitle", parent=styles["Title"], fontName="HYGothic-Medium", fontSize=18, leading=23, textColor=colors.HexColor("#0E2372"), spaceAfter=5)
    sub = ParagraphStyle("MSub", parent=styles["Normal"], fontName="HYGothic-Medium", fontSize=8.5, leading=12, textColor=colors.HexColor("#5A6677"), spaceAfter=8)
    head = ParagraphStyle("MHead", parent=styles["Heading2"], fontName="HYGothic-Medium", fontSize=12, leading=15, textColor=colors.HexColor("#0F1722"), spaceBefore=6, spaceAfter=5)
    body = ParagraphStyle("MBody", parent=styles["BodyText"], fontName="HYGothic-Medium", fontSize=9, leading=13, textColor=colors.HexColor("#202A38"))
    small = ParagraphStyle("MSmall", parent=body, fontSize=8.1, leading=11.5, textColor=colors.HexColor("#3E4A5A"))

    def make_table(data, widths):
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "HYGothic-Medium"),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0E2372")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTSIZE", (0, 0), (-1, 0), 8.2),
            ("FONTSIZE", (0, 1), (-1, -1), 7.8),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E0EA")),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F7F9FC")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    def plain_text(value):
        return re.sub("<.*?>", "", str(value))

    def pdf_text(value):
        return html.escape(plain_text(value))

    story = [
        Paragraph("KCC Glass LVT Monthly Intelligence Report", title),
        Paragraph(f"Monthly report | {datetime.now().strftime('%Y-%m-%d %H:%M')} 기준 | Overview · Freight · Raw Materials · Design Trend", sub),
        Paragraph("1. Executive Summary", head),
        Paragraph(pdf_text(summary["headline"]), body),
        Spacer(1, 5),
    ]

    metric_table = [["지표", "현재값", "변화/비고"]] + metrics
    story.extend([
        make_table(metric_table, [43*mm, 42*mm, 87*mm]),
        Spacer(1, 6),
        Paragraph("2. Risk Signals", head),
    ])
    if alerts:
        for a in alerts[:5]:
            story.append(Paragraph(pdf_text(f"- {a['title']} {a['value']}: {a['message']}"), small))
    else:
        story.append(Paragraph("- 주요 임계값 초과 항목은 없습니다.", small))

    story.extend([Spacer(1, 5), Paragraph("3. Recommended Actions", head)])
    action_data = [["영역", "권고 액션"]] + action_recs[["영역", "권고 액션"]].astype(str).values.tolist()
    story.append(make_table(action_data, [30*mm, 142*mm]))

    story.extend([PageBreak(), Paragraph("4. Freight &amp; Raw Materials", head)])
    freight_data = [["지표", "단위", "기준일", "현재", "전월대비", "전년대비"]]
    for r in freight_rows:
        freight_data.append([r["label"], r["unit"], r["date"], r["current"], plain_text(r["mom"]), plain_text(r["yoy"])])
    story.extend([Paragraph("Freight Index", small), make_table(freight_data, [28*mm, 24*mm, 31*mm, 29*mm, 30*mm, 30*mm]), Spacer(1, 7)])

    raw_data = [["지표", "단위", "기준월/일", "현재", "전월대비", "전년대비"]]
    for r in raw_rows:
        raw_data.append([r["label"], r["unit"], r["date"], r["current"], plain_text(r["mom"]), plain_text(r["yoy"])])
    story.extend([Paragraph("Raw Materials / FX", small), make_table(raw_data, [28*mm, 27*mm, 31*mm, 29*mm, 28*mm, 29*mm])])

    story.extend([
        Spacer(1, 7),
        Paragraph("Management Note", head),
        Paragraph(pdf_text(f"- 원자재: {summary['cost']}"), small),
        Paragraph(pdf_text(f"- 환율: {summary['fx']}"), small),
    ])

    story.extend([PageBreak(), Paragraph("5. Design Trend Intelligence", head)])
    kw_data = [["Keyword", "Mentions"]] + keyword_df.head(8).astype(str).values.tolist()
    story.extend([Paragraph("Trend Keyword Radar", small), make_table(kw_data, [90*mm, 35*mm]), Spacer(1, 7)])
    imp_data = [["Trend", "Signal", "Product Implication"]]
    for _, r in implication_df.head(8).iterrows():
        imp_data.append([str(r["Trend"]), str(r["Signal"]), str(r["Product Implication"])])
    story.extend([Paragraph("Product Implication", small), make_table(imp_data, [36*mm, 20*mm, 116*mm])])

    if comment_df is not None and not comment_df.empty:
        story.extend([Spacer(1, 7), Paragraph("6. Monthly Comment Log", head)])
        cdf = comment_df.head(6).astype(str)
        comment_data = [["월", "카테고리", "코멘트", "작성/수정"]] + cdf[["월", "카테고리", "코멘트", "작성/수정"]].values.tolist()
        story.append(make_table(comment_data, [22*mm, 28*mm, 88*mm, 34*mm]))

    doc.build(story)
    buffer.seek(0)
    return buffer

def clean_export_df(df):
    export = df.copy()
    for col in export.columns:
        if pd.api.types.is_datetime64_any_dtype(export[col]):
            export[col] = export[col].dt.strftime("%Y-%m-%d")
    return export

def make_excel_file(sheets):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            safe_name = sheet_name[:31]
            clean_export_df(df).to_excel(writer, sheet_name=safe_name, index=False)
            ws = writer.sheets[safe_name]
            ws.freeze_panes = "A2"
            for column_cells in ws.columns:
                max_len = 0
                col_letter = column_cells[0].column_letter
                for cell in column_cells:
                    max_len = max(max_len, len(str(cell.value)) if cell.value is not None else 0)
                ws.column_dimensions[col_letter].width = min(max(max_len + 2, 10), 22)
    buffer.seek(0)
    return buffer

def excel_download_button(label, sheets, file_name, key):
    st.download_button(
        label,
        data=make_excel_file(sheets),
        file_name=file_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        key=key,
    )

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
df_permits  = get_fred('PERMIT',       '건축허가')
df_complete = get_fred('COMPUTSA',     '주택완공')
df_month_supply = get_fred('MSACSR',   '신규주택재고개월')
df_existing_sales = get_fred('EXHOSLUSM495S', '기존주택판매')
df_building_retail = get_fred('MRTSSM4441USN', '건자재유통매출')
df_lumber_ppi = get_fred('WPU081',     'Lumber PPI')
df_building_ppi = get_fred('PCU44414441', '건자재유통PPI')
df_wti      = get_fred('DCOILWTICO',    'WTI')
df_brent    = get_fred('DCOILBRENTEU',  'Brent')
df_fx       = get_fred('DEXKOUS',       'USD/KRW')
usd_krw     = get_exchange_rate()
init_session_state(usd_krw)
df_purchase = get_purchase_price_df()
df_freight  = get_freight_index_df()
df_market   = get_market_insight_df()

v_housing  = latest(df_housing,  '주택착공')
v_mortgage = latest(df_mortgage, '모기지금리')
v_cpi      = latest(df_cpi,      'CPI')
v_fedfunds = latest(df_fedfunds, '기준금리')
v_permits  = latest(df_permits,  '건축허가')
v_complete = latest(df_complete, '주택완공')
v_supply   = latest(df_month_supply, '신규주택재고개월')
v_existing = latest(df_existing_sales, '기존주택판매')
v_building_retail = latest(df_building_retail, '건자재유통매출')
v_lumber_ppi = latest(df_lumber_ppi, 'Lumber PPI')
v_building_ppi = latest(df_building_ppi, '건자재유통PPI')
v_wti      = latest(df_wti,      'WTI')
v_brent    = latest(df_brent,    'Brent')
v_fx_hist  = latest(df_fx,       'USD/KRW')
v_pvc      = latest(df_purchase, 'PVC')
v_dotp     = latest(df_purchase, 'DOTP')
v_scfi     = latest(df_freight,  'SCFI')
v_ccfi     = latest(df_freight,  'CCFI')
d_housing  = delta_pct(df_housing,  '주택착공')
d_mortgage = delta_pct(df_mortgage, '모기지금리')
d_cpi      = delta_pct(df_cpi,      'CPI')
d_permits  = delta_pct(df_permits,  '건축허가')
d_complete = delta_pct(df_complete, '주택완공')
d_supply   = delta_pct(df_month_supply, '신규주택재고개월')
d_existing = delta_pct(df_existing_sales, '기존주택판매')
d_building_retail = delta_pct(df_building_retail, '건자재유통매출')
d_lumber_ppi = delta_pct(df_lumber_ppi, 'Lumber PPI')
d_building_ppi = delta_pct(df_building_ppi, '건자재유통PPI')
d_wti      = delta_pct(df_wti,      'WTI')
d_brent    = delta_pct(df_brent,    'Brent')
d_fx       = delta_pct(df_fx,       'USD/KRW', periods=20)
d_pvc      = delta_pct(df_purchase, 'PVC')
d_dotp     = delta_pct(df_purchase, 'DOTP')
d_scfi     = delta_pct(df_freight,  'SCFI', periods=4)
d_ccfi     = delta_pct(df_freight,  'CCFI', periods=4)

def chart_layout(fig, height=240):
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color=T['text2'], size=11),
        margin=dict(l=10, r=60, t=10, b=10), height=height,
        legend=dict(bgcolor='rgba(0,0,0,0)', font=dict(color=T['text2'], size=10),
                    orientation='h', yanchor='bottom', y=1.0, xanchor='left', x=0),
        xaxis=dict(gridcolor=T['chart_grid'], showgrid=False),
        yaxis=dict(gridcolor=T['chart_grid']),
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=T['panel2'],
            bordercolor=T['accent'],
            font=dict(color=T['text'], size=fs(12)),
        ),
    )
    return fig

CHART_CONFIG = {
    "displayModeBar": True,
    "displaylogo": False,
    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
    "toImageButtonOptions": {
        "format": "png",
        "filename": "kcc_lvt_chart",
        "height": 720,
        "width": 1280,
        "scale": 2,
    },
}

def home_sparkline(df, col, color="#E8B339", points=24):
    try:
        values = pd.to_numeric(df[col], errors="coerce").dropna().tail(points).tolist()
        if len(values) < 2:
            return '<svg class="sparkline" viewBox="0 0 140 34"></svg>'
        width, height, pad = 140, 34, 3
        low, high = min(values), max(values)
        span = high - low if high != low else 1
        coords = []
        for i, value in enumerate(values):
            x = pad + (width - pad * 2) * i / (len(values) - 1)
            y = height - pad - ((value - low) / span) * (height - pad * 2)
            coords.append(f"{x:.1f},{y:.1f}")
        area = f"{pad},{height-pad} " + " ".join(coords) + f" {width-pad},{height-pad}"
        return (
            f'<svg class="sparkline" viewBox="0 0 {width} {height}" preserveAspectRatio="none">'
            f'<polygon points="{area}" fill="{color}" opacity="0.13"></polygon>'
            f'<polyline points="{" ".join(coords)}" fill="none" stroke="{color}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"></polyline>'
            f'<circle cx="{coords[-1].split(",")[0]}" cy="{coords[-1].split(",")[1]}" r="2.6" fill="{color}"></circle>'
            f'</svg>'
        )
    except Exception:
        return '<svg class="sparkline" viewBox="0 0 140 34"></svg>'

def build_home_insight(summary, alerts, d_fx, d_scfi, d_pvc, d_dotp):
    if alerts:
        top = alerts[0]
        return f"{top['title']}가 {top['value']} 수준입니다. {top['message']}"
    if d_scfi >= 8 and d_fx >= 1:
        return "운임과 환율이 동시에 상승 흐름입니다. 신규 견적은 유효기간과 비용 전가 타이밍을 짧게 관리하는 편이 좋습니다."
    if d_pvc >= 5 or d_dotp >= 5:
        return "PVC/DOTP 구매 지수가 올라오고 있습니다. 원가 반영 필요성과 고객별 가격 민감도를 함께 점검하세요."
    return summary["headline"]

# ════════════════════════════════════════════════════════════
# 사이드바
# ════════════════════════════════════════════════════════════
MENU_GROUPS = {
    "🏠 Home": ["🏠 Home"],
    "📊 Overview": ["📊 Overview"],
    "💼 Sales Intelligence": ["🎯 Market Insight", "🗺 Account Map", "🏭 Competitor Export", "💱 FX/Tariff"],
    "🚢 Cost & Logistics": ["🛢 원자재", "🚢 Freight"],
    "🎨 Design & News": ["🎨 Design Intelligence", "📰 FCW News"],
    "🏡 Macro / Housing": ["🏡 Housing", "📈 Macro"],
}
PAGE_TO_GROUP = {
    page: group
    for group, pages in MENU_GROUPS.items()
    for page in pages
}

def go_to_menu(target):
    st.session_state.main_menu_group = PAGE_TO_GROUP.get(target, "🏠 Home")
    st.session_state.main_menu = target

with st.sidebar:
    st.markdown('<div class="sb-brand">LVT INTELLIGENCE</div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-sub">KCC Glass · Overseas Sales</div>', unsafe_allow_html=True)
    if "main_menu_group" not in st.session_state:
        st.session_state.main_menu_group = "🏠 Home"
    if st.session_state.main_menu_group not in MENU_GROUPS:
        st.session_state.main_menu_group = "🏠 Home"

    if "main_menu" not in st.session_state:
        st.session_state.main_menu = MENU_GROUPS[st.session_state.main_menu_group][0]
    if st.session_state.main_menu not in PAGE_TO_GROUP:
        st.session_state.main_menu = "🏠 Home"
    st.session_state.main_menu_group = PAGE_TO_GROUP.get(st.session_state.main_menu, "🏠 Home")

    st.markdown('<div class="sb-nav-label">Workspace</div>', unsafe_allow_html=True)
    for group_name, group_pages in MENU_GROUPS.items():
        active_group = st.session_state.main_menu_group == group_name
        with st.expander(group_name, expanded=active_group):
            for page_name in group_pages:
                if page_name == st.session_state.main_menu:
                    st.markdown(f'<div class="sb-active-page">{page_name}</div>', unsafe_allow_html=True)
                else:
                    st.button(
                        page_name,
                        key=f"nav_{re.sub(r'[^0-9A-Za-z가-힣]+', '_', page_name)}",
                        use_container_width=True,
                        on_click=go_to_menu,
                        args=(page_name,),
                    )
            if active_group and len(group_pages) > 1:
                label = re.sub(r"^[^\w가-힣]+", "", group_name).strip()
                st.markdown(f'<div class="sb-subnav">{label} 안에서 필요한 세부 화면을 선택합니다.</div>', unsafe_allow_html=True)
    menu = st.session_state.main_menu

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    # 테마 토글
    theme_label = "🌙 다크 모드" if st.session_state.theme == "light" else "☀️ 라이트 모드"
    if st.button(theme_label, use_container_width=True):
        st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"
        st.rerun()

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
    st.radio(
        "글자 크기",
        ["기본", "크게", "아주 크게"],
        key="font_size_mode",
        horizontal=False,
    )

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

scfi_val = v_scfi or st.session_state.get("scfi_now", 2543)
ticker_html = (
    tk("USD/KRW", f"{usd_krw:,.0f}") +
    tk("30Y MTG", f"{v_mortgage:.2f}%") +
    tk("FED FUNDS", f"{v_fedfunds:.2f}%") +
    tk("SCFI", f"{scfi_val:,.0f}", "tk-up" if d_scfi > 0 else "tk-dn") +
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
# 🏠 HOME
# ════════════════════════════════════════════════════════════
if menu == "🏠 Home":
    home_summary = build_market_summary(
        v_housing, d_housing, v_mortgage, d_mortgage, v_cpi, d_cpi,
        v_fedfunds, usd_krw, v_wti, d_wti
    )
    home_alerts = build_alerts(usd_krw, v_wti, d_wti, v_mortgage, v_scfi, d_scfi, d_pvc, d_dotp)
    top_alert = home_alerts[0] if home_alerts else {"title": "Normal", "value": "OK", "message": "주요 임계값 초과 항목은 없습니다."}
    home_insight = build_home_insight(home_summary, home_alerts, d_fx, d_scfi, d_pvc, d_dotp)
    home_actions = build_action_recommendations(home_alerts, usd_krw, v_scfi, d_scfi, v_mortgage, d_pvc, d_dotp)
    home_action_area = home_actions.iloc[0]["영역"] if len(home_actions) else "운영"
    home_action_text = home_actions.iloc[0]["권고 액션"] if len(home_actions) else "주요 지표를 주간 단위로 점검하세요."
    fx_spark = home_sparkline(df_fx, "USD/KRW", GOLD)
    scfi_spark = home_sparkline(df_freight, "SCFI", "#4ADE80")
    wti_spark = home_sparkline(df_wti, "WTI", "#FF6B6E")
    mtg_spark = home_sparkline(df_mortgage, "모기지금리", "#7AA7FF")
    hero_logo = f'<img class="home-logo" src="data:image/png;base64,{LOGO_WHITE}"/>' if LOGO_WHITE else '<div class="home-logo" style="color:#fff;font-weight:900;font-size:24px">KCC GLASS</div>'
    st.markdown(f"""
    <section class="home-hero">
      <div class="home-bg"></div>
      <div class="home-bg"></div>
      <div class="home-bg"></div>
      <div class="home-bg"></div>
      <div class="home-content">
        {hero_logo}
        <div class="home-eyebrow">Global LVT Market Intelligence Platform</div>
        <div class="home-title">미국 LVT 시장을 한 화면에서 읽고, 바로 실행합니다.</div>
        <div class="home-copy">
          영업, 물류, 구매, 디자인팀이 같은 시장 지표와 뉴스를 보고 의사결정할 수 있도록 만든
          KCC Glass 해외영업 통합 인텔리전스 터미널입니다.
        </div>
        <div class="home-insight"><span class="home-insight-badge">Today Insight</span><span>{html.escape(home_insight)}</span></div>
        <div class="home-metrics">
          <div class="home-metric"><div class="home-metric-k">USD/KRW</div><div class="home-metric-v">{usd_krw:,.0f}</div><div class="home-metric-c">20거래일 {d_fx:+.1f}%</div>{fx_spark}</div>
          <div class="home-metric"><div class="home-metric-k">SCFI</div><div class="home-metric-v">{v_scfi:,.0f}</div><div class="home-metric-c">4주 {d_scfi:+.1f}%</div>{scfi_spark}</div>
          <div class="home-metric"><div class="home-metric-k">WTI</div><div class="home-metric-v">{v_wti:.1f}</div><div class="home-metric-c">원자재 비용 신호</div>{wti_spark}</div>
          <div class="home-metric"><div class="home-metric-k">30Y Mortgage</div><div class="home-metric-v">{v_mortgage:.2f}%</div><div class="home-metric-c">수요 심리 지표</div>{mtg_spark}</div>
        </div>
      </div>
    </section>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="home-command-grid">
      <div class="home-command-card">
        <div class="home-command-k">Market Pulse</div>
        <div class="home-command-v">오늘의 시장 한 줄</div>
        <div class="home-command-c">{html.escape(home_summary["headline"])}</div>
      </div>
      <div class="home-command-card">
        <div class="home-command-k">Cost Watch</div>
        <div class="home-command-v">PVC {d_pvc:+.1f}% · DOTP {d_dotp:+.1f}%</div>
        <div class="home-command-c">WTI {v_wti:.1f}, USD/KRW {usd_krw:,.0f}. 구매/견적 원가 전제 점검 구간입니다.</div>
      </div>
      <div class="home-command-card">
        <div class="home-command-k">Logistics Signal</div>
        <div class="home-command-v">SCFI {v_scfi:,.0f}</div>
        <div class="home-command-c">4주 변동 {d_scfi:+.1f}%. 선복, 운임 유효기간, 출고 타이밍을 함께 확인하세요.</div>
      </div>
      <div class="home-command-card">
        <div class="home-command-k">Recommended Action · {html.escape(str(home_action_area))}</div>
        <div class="home-command-v">다음 실행 포인트</div>
        <div class="home-command-c">{html.escape(str(home_action_text))}</div>
      </div>
    </div>
    <div class="home-workflow">
      <div class="home-step"><div class="home-step-no">01</div><div><div class="home-step-t">시장 신호 확인</div><div class="home-step-d">Overview에서 수요, 환율, 금리와 경고 신호를 먼저 봅니다.</div></div></div>
      <div class="home-step"><div class="home-step-no">02</div><div><div class="home-step-t">비용 압박 점검</div><div class="home-step-d">원자재와 운임 지수로 견적 전제를 업데이트합니다.</div></div></div>
      <div class="home-step"><div class="home-step-no">03</div><div><div class="home-step-t">경쟁사/거래선 확인</div><div class="home-step-d">타깃 거래선과 ImportYeti 업로드 자료로 시장 움직임을 봅니다.</div></div></div>
      <div class="home-step"><div class="home-step-no">04</div><div><div class="home-step-t">보고서로 마감</div><div class="home-step-d">월간 PDF에 핵심 지표와 액션을 묶어 상부 보고에 사용합니다.</div></div></div>
    </div>
    """, unsafe_allow_html=True)

    h1, h2 = st.columns([1.45, 1], gap="medium")
    with h1:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Team Entry</span><span class="p-m">Choose your workflow</span></div><div class="p-body">', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="home-entry-grid">
          <div class="home-entry"><div class="home-entry-icon">📊</div><div class="home-entry-k">Sales</div><div class="home-entry-t">Market Overview</div><div class="home-entry-d">상부 보고와 영업 메시지에 필요한 핵심 지표 요약</div></div>
          <div class="home-entry"><div class="home-entry-icon">🏭</div><div class="home-entry-k">Competition</div><div class="home-entry-t">Export Tracker</div><div class="home-entry-d">B/L Weight 기준 국내 경쟁사 미국 수출 동향 추정</div></div>
          <div class="home-entry"><div class="home-entry-icon">🚢</div><div class="home-entry-k">Logistics</div><div class="home-entry-t">Freight Monitor</div><div class="home-entry-d">SCFI/CCFI, 운임 뉴스, 선적 리스크 체크</div></div>
          <div class="home-entry"><div class="home-entry-icon">🎨</div><div class="home-entry-k">Design</div><div class="home-entry-t">Design Trend</div><div class="home-entry-d">FCW/FCNews 기반 디자인 키워드와 제품 적용 포인트</div></div>
          <div class="home-entry"><div class="home-entry-icon">🛢</div><div class="home-entry-k">Purchase</div><div class="home-entry-t">Raw Materials</div><div class="home-entry-d">PVC, DOTP, WTI, 환율 흐름과 전월/전년 비교</div></div>
        </div>
        """, unsafe_allow_html=True)
        b1, b2, b3, b4, b5 = st.columns(5)
        with b1:
            st.button("Overview", use_container_width=True, on_click=go_to_menu, args=("📊 Overview",), key="home_to_overview")
        with b2:
            st.button("경쟁사", use_container_width=True, on_click=go_to_menu, args=("🏭 Competitor Export",), key="home_to_competitor")
        with b3:
            st.button("Freight", use_container_width=True, on_click=go_to_menu, args=("🚢 Freight",), key="home_to_freight")
        with b4:
            st.button("Design", use_container_width=True, on_click=go_to_menu, args=("🎨 Design Intelligence",), key="home_to_design")
        with b5:
            st.button("원자재", use_container_width=True, on_click=go_to_menu, args=("🛢 원자재",), key="home_to_raw")
        st.markdown('</div></div>', unsafe_allow_html=True)

    with h2:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Today Signal</span><span class="p-m">Executive snapshot</span></div><div class="p-body">', unsafe_allow_html=True)
        st.markdown(f"""
        <div class="home-signal-grid">
          <div class="home-signal"><div class="home-signal-k">Headline</div><div class="home-signal-v">{html.escape(home_summary["headline"])}</div></div>
          <div class="home-signal"><div class="home-signal-k">Top Risk</div><div class="home-signal-v">{html.escape(top_alert["title"])} {html.escape(top_alert["value"])}<br>{html.escape(top_alert["message"])}</div></div>
          <div class="home-signal"><div class="home-signal-k">Next Move</div><div class="home-signal-v">Overview에서 실행 액션, 경고 신호, AI 브리핑을 함께 확인하세요.</div></div>
        </div>
        <div class="home-report-card">
          <div class="home-report-k">Executive Report</div>
          <div class="home-report-t">이번 달 보고서 생성</div>
          <div class="home-report-d">Overview · Freight · Raw Materials · Design Trend를 묶은 월간 종합 PDF를 바로 내려받을 수 있습니다.</div>
        </div>
        """, unsafe_allow_html=True)
        st.button("월간 PDF 보고서로 이동", use_container_width=True, on_click=go_to_menu, args=("📊 Overview",), key="home_to_report")
        st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Platform Role</span><span class="p-m">Shared operating view</span></div><div class="p-body">', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="summary-grid">
      <div class="summary-card"><div class="summary-k">영업팀</div><div class="summary-v">환율, 주택시장, 관세, 타깃 거래선을 묶어 고객 미팅 전 시장 메시지를 정리합니다.</div></div>
      <div class="summary-card"><div class="summary-k">물류팀</div><div class="summary-v">운임 지수와 뉴스 흐름을 통해 선적 타이밍과 운임 리스크를 사전에 공유합니다.</div></div>
      <div class="summary-card"><div class="summary-k">구매/디자인팀</div><div class="summary-v">PVC/DOTP 지수와 미국 디자인 키워드를 함께 보며 제품·가격 전략의 근거를 만듭니다.</div></div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="esg-card">
          <div class="esg-k">Official Company Resource</div>
          <div class="esg-t">KCC Glass ESG Resource</div>
          <div class="esg-d">
            최신 2024/25 ESG Report를 업무용 관점으로 압축했습니다.
            PDF 원문은 공식 링크로 열고, 아래 요약은 해외 고객 대응과 내부 참고용 quick brief로 활용하세요.
          </div>
          <div class="esg-tags">
            <span class="esg-tag">Sustainable Life</span>
            <span class="esg-tag">Environmental</span>
            <span class="esg-tag">Supply Chain</span>
            <span class="esg-tag">Customer Satisfaction</span>
            <span class="esg-tag">Social Contribution</span>
          </div>
          <div class="esg-summary-grid">
            {''.join([
                f'<div class="esg-summary-card"><div class="esg-summary-k">{html.escape(item["axis"])}</div><div class="esg-summary-v">{html.escape(item["message"])}</div><div class="esg-summary-u">{html.escape(item["use"])}</div></div>'
                for item in ESG_SUMMARY_ITEMS
            ])}
          </div>
          <div class="esg-actions">
            <a class="esg-btn" href="{KCC_ESG_LATEST_KO_URL}" target="_blank" rel="noopener noreferrer">2024/25 Korean Report</a>
            <a class="esg-btn" href="{KCC_ESG_LATEST_EN_URL}" target="_blank" rel="noopener noreferrer">2024/25 English Report</a>
            <a class="esg-btn secondary" href="{KCC_ESG_REPORT_PAGE_KO}" target="_blank" rel="noopener noreferrer">Official ESG Archive</a>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# ════════════════════════════════════════════════════════════
# 📊 OVERVIEW
# ════════════════════════════════════════════════════════════
elif menu == "📊 Overview":
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

    v_newsales = latest(df_newsales, "신규주택판매")
    market_summary = build_market_summary(
        v_housing, d_housing, v_mortgage, d_mortgage, v_cpi, d_cpi,
        v_fedfunds, usd_krw, v_wti, d_wti
    )
    alerts = build_alerts(usd_krw, v_wti, d_wti, v_mortgage, v_scfi, d_scfi, d_pvc, d_dotp)
    weekly_brief = build_weekly_brief(market_summary, alerts, d_fx, d_scfi, d_pvc, d_dotp)
    action_recs = build_action_recommendations(alerts, usd_krw, v_scfi, d_scfi, v_mortgage, d_pvc, d_dotp)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Alert / Warning Center</span><span class="p-m">Threshold watch</span></div><div class="p-body">', unsafe_allow_html=True)
    st.markdown(render_alert_cards(alerts), unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Action Recommendation Box</span><span class="p-m">What to do next</span></div><div class="p-body">', unsafe_allow_html=True)
    st.markdown(dataframe_to_dark_table(action_recs), unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

    watch_items = list(build_watchlist_items().keys())
    selected_watch = st.multiselect(
        "Watchlist",
        watch_items,
        default=["USD/KRW", "SCFI", "PVC", "30Y Mortgage", "Tariff"],
        label_visibility="collapsed",
        key="overview_watchlist",
    )
    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">My Watchlist</span><span class="p-m">Focus indicators</span></div><div class="p-body">', unsafe_allow_html=True)
    st.markdown(render_watchlist(selected_watch), unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

    board_mode = st.checkbox("Board Report Mode", value=False, help="상부 보고용으로 핵심 항목만 압축해서 봅니다.")
    if board_mode:
        top_news = llm.fetch_news("freight", limit=3)
        news_lines = "<br>".join([f'{i+1}. {html.escape(n.get("title", ""))}' for i, n in enumerate(top_news[:3])]) or "주요 뉴스 없음"
        alert_line = "<br>".join([f'{html.escape(a["title"])}: {html.escape(a["value"])}' for a in alerts[:3]]) or "주요 임계값 초과 없음"
        action_line = "<br>".join([f'{i+1}. {html.escape(r["권고 액션"])}' for i, (_, r) in enumerate(action_recs.head(3).iterrows())])
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Board Report View</span><span class="p-m">One-page executive mode</span></div><div class="p-body">', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="board-grid">
              <div class="board-card"><div class="board-k">Headline</div><div class="board-v">{html.escape(market_summary["headline"])}</div></div>
              <div class="board-card"><div class="board-k">Risk Signals</div><div class="board-v">{alert_line}</div></div>
              <div class="board-card"><div class="board-k">Action Points</div><div class="board-v">{action_line}</div></div>
            </div>
            <div class="board-grid">
              <div class="board-card"><div class="board-k">Core Metrics</div><div class="board-v">USD/KRW {usd_krw:,.0f}<br>SCFI {v_scfi:,.0f}<br>PVC {v_pvc:,.2f}<br>30Y Mortgage {v_mortgage:.2f}%</div></div>
              <div class="board-card"><div class="board-k">Weekly Brief</div><div class="board-v">{"<br>".join([html.escape(x) for x in weekly_brief[:3]])}</div></div>
              <div class="board-card"><div class="board-k">Top Freight News</div><div class="board-v">{news_lines}</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('</div></div>', unsafe_allow_html=True)

    b_col, u_col = st.columns([1.2, 1], gap="medium")
    with b_col:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Weekly Executive Brief</span><span class="p-m">5-line summary</span></div><div class="p-body">', unsafe_allow_html=True)
        brief_rows = "".join([f"<tr><td>{i}</td><td>{html.escape(line)}</td></tr>" for i, line in enumerate(weekly_brief, 1)])
        st.markdown(f'<table class="dt"><thead><tr><th>No.</th><th>이번 주 핵심 변화</th></tr></thead><tbody>{brief_rows}</tbody></table>', unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)
    with u_col:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Source & Last Updated</span><span class="p-m">Data health</span></div><div class="p-body">', unsafe_allow_html=True)
        st.markdown(dataframe_to_dark_table(build_update_rows()), unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

    with st.expander("Data Update Center — 구매팀/물류팀 엑셀을 임시 반영"):
        up1, up2 = st.columns(2, gap="medium")
        with up1:
            purchase_file = st.file_uploader("PVC/DOTP 월별 지수 업로드", type=["xlsx", "xls"], key="purchase_upload")
            if purchase_file is not None:
                try:
                    uploaded_purchase = normalize_purchase_upload(purchase_file)
                    set_purchase_price_df(uploaded_purchase)
                    st.success("PVC/DOTP 지수를 현재 세션에 반영했습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(f"PVC/DOTP 업로드 형식을 확인해주세요: {e}")
        with up2:
            freight_file = st.file_uploader("SCFI/CCFI 운임 지수 업로드", type=["xlsx", "xls"], key="freight_upload")
            if freight_file is not None:
                try:
                    uploaded_freight = pd.read_excel(freight_file)
                    set_freight_index_df(uploaded_freight)
                    st.success("SCFI/CCFI 지수를 현재 세션에 반영했습니다.")
                    st.rerun()
                except Exception as e:
                    st.error(f"운임 지수 업로드 형식을 확인해주세요: {e}")
        st.caption("업로드 반영은 현재 접속 세션 기준입니다. 팀 전체에 고정 반영하려면 업데이트된 데이터를 코드/JSON에 반영해 GitHub에 다시 올리는 방식이 가장 안정적입니다.")

    with st.expander("Monthly Comment Log — 월별 시장 판단 기록"):
        default_month = datetime.now().strftime("%Y-%m")
        log_col1, log_col2 = st.columns([1, 1], gap="medium")
        with log_col1:
            log_month = st.text_input("기준월", value=default_month, key="comment_month")
        with log_col2:
            log_category = st.selectbox("카테고리", ["Overview", "Raw Materials", "Freight", "Housing", "Macro", "FX/Tariff", "Market Insight"], key="comment_category")
        existing_log = get_comment_log_df()
        existing_text = ""
        if not existing_log.empty:
            matched = existing_log[(existing_log["월"] == log_month) & (existing_log["카테고리"] == log_category)]
            if len(matched):
                existing_text = matched.iloc[0]["코멘트"]
        log_text = st.text_area("코멘트", value=existing_text, height=110, key="comment_text")
        if st.button("코멘트 저장", use_container_width=True, key="save_monthly_comment"):
            if log_text.strip():
                save_monthly_comment(log_month[:7], log_category, log_text)
                st.success("월별 코멘트를 저장했습니다. 현재 접속 세션 기준으로 유지됩니다.")
                st.rerun()
            else:
                st.warning("저장할 코멘트를 입력해주세요.")
        log_df = get_comment_log_df()
        if not log_df.empty:
            st.markdown(dataframe_to_dark_table(log_df), unsafe_allow_html=True)
            excel_download_button(
                "📊 코멘트 로그 엑셀 다운로드",
                {"Monthly Comment Log": log_df},
                f"kcc_lvt_comment_log_{datetime.now().strftime('%Y%m%d')}.xlsx",
                "comment_log_excel_download",
            )
        else:
            st.caption("아직 저장된 코멘트가 없습니다. 월별 회의나 보고 후 판단 근거를 남겨두면 다음 달 비교가 쉬워집니다.")

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
        fig.add_trace(go.Bar(
            x=dfh["date"], y=dfh["주택착공"], name="Housing Starts (K)",
            marker_color=T['accent'], opacity=0.7,
            hovertemplate="%{x|%Y-%m-%d}<br>Housing Starts: %{y:,.0f}K<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=dfm["date"], y=dfm["모기지금리"], name="30Y Rate (%)", yaxis="y2",
            line=dict(color=T['down'], width=2.5),
            hovertemplate="%{x|%Y-%m-%d}<br>30Y Mortgage: %{y:.2f}%<extra></extra>",
        ))
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
        st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
        overview_housing_rows = [
            indicator_compare_row("Housing Starts", df_housing, "주택착공", "K", 0),
            indicator_compare_row("New Home Sales", df_newsales, "신규주택판매", "K", 0),
            indicator_compare_row("30Y Mortgage", df_mortgage, "모기지금리", "%", 2),
        ]
        st.markdown(
            f"""
            <table class="dt">
              <thead>
                <tr>
                  <th>지표</th><th>단위</th><th>기준일</th><th>현재</th>
                  <th>전월</th><th>전월대비</th><th>전년</th><th>전년대비</th>
                </tr>
              </thead>
              <tbody>{build_market_compare_rows(overview_housing_rows)}</tbody>
            </table>
            """,
            unsafe_allow_html=True,
        )
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
        st.plotly_chart(fig_fx, use_container_width=True, config=CHART_CONFIG)
        st.markdown(
            f'<div style="color:{T["text3"]};font-size:11px;margin-top:-4px">FRED 일별 환율 흐름에 현재 실시간 환율 {usd_krw:,.0f}원을 점선으로 표시합니다.</div>',
            unsafe_allow_html=True,
        )
        fx_rows = [
            indicator_compare_row("USD/KRW", df_fx, "USD/KRW", "KRW/USD", 0, current_override=usd_krw),
        ]
        st.markdown(
            f"""
            <table class="dt" style="margin-top:10px">
              <thead>
                <tr>
                  <th>지표</th><th>단위</th><th>기준일</th><th>현재</th>
                  <th>전월</th><th>전월대비</th><th>전년</th><th>전년대비</th>
                </tr>
              </thead>
              <tbody>{build_market_compare_rows(fx_rows)}</tbody>
            </table>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="placeholder"><span style="font-size:26px">💱</span><span>환율 시계열을 불러올 수 없습니다</span></div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">PVC / DOTP Purchase Index</span><span class="p-m">Purchasing team · Monthly</span></div><div class="p-body">', unsafe_allow_html=True)
    dfp_recent = df_purchase.tail(14)
    if len(dfp_recent):
        fig_raw_idx = go.Figure()
        fig_raw_idx.add_trace(go.Scatter(
            x=dfp_recent["date"], y=dfp_recent["PVC"], name="PVC",
            mode="lines+markers", line=dict(color=T['accent'], width=2.5),
            hovertemplate="%{x|%Y-%m}<br>PVC: %{y:,.2f}<extra></extra>",
        ))
        fig_raw_idx.add_trace(go.Scatter(
            x=dfp_recent["date"], y=dfp_recent["DOTP"], name="DOTP",
            mode="lines+markers", line=dict(color=GOLD, width=2.5),
            hovertemplate="%{x|%Y-%m}<br>DOTP: %{y:,.2f}<extra></extra>",
        ))
        chart_layout(fig_raw_idx, 230)
        fig_raw_idx.update_layout(hovermode="x unified")
        st.plotly_chart(fig_raw_idx, use_container_width=True, config=CHART_CONFIG)
        pvc_row = purchase_compare_row("PVC", df_purchase, "PVC")
        dotp_row = purchase_compare_row("DOTP", df_purchase, "DOTP")
        st.markdown(
            f"""
            <table class="dt">
              <thead><tr><th>지표</th><th>단위</th><th>기준월</th><th>현재</th><th>전월</th><th>전월대비</th><th>전년</th><th>전년대비</th></tr></thead>
              <tbody>{build_market_compare_rows([pvc_row, dotp_row])}</tbody>
            </table>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="placeholder"><span style="font-size:26px">🧪</span><span>PVC/DOTP 구매팀 지수를 입력하면 표시됩니다</span></div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">SCFI / CCFI Freight Index</span><span class="p-m">NLIC · Weekly</span></div><div class="p-body">', unsafe_allow_html=True)
    dff_recent = df_freight.tail(52)
    if len(dff_recent):
        fig_freight_ov = go.Figure()
        fig_freight_ov.add_trace(go.Scatter(
            x=dff_recent["date"], y=dff_recent["SCFI"], name="SCFI",
            mode="lines+markers", line=dict(color=T['accent'], width=2.5),
            hovertemplate="%{x|%Y-%m-%d}<br>SCFI: %{y:,.2f}<extra></extra>",
        ))
        fig_freight_ov.add_trace(go.Scatter(
            x=dff_recent["date"], y=dff_recent["CCFI"], name="CCFI",
            mode="lines+markers", line=dict(color=GOLD, width=2.5),
            hovertemplate="%{x|%Y-%m-%d}<br>CCFI: %{y:,.2f}<extra></extra>",
        ))
        chart_layout(fig_freight_ov, 230)
        fig_freight_ov.update_layout(hovermode="x unified")
        st.plotly_chart(fig_freight_ov, use_container_width=True, config=CHART_CONFIG)
        scfi_row = freight_compare_row("SCFI", df_freight, "SCFI")
        ccfi_row = freight_compare_row("CCFI", df_freight, "CCFI")
        st.markdown(
            f"""
            <table class="dt">
              <thead><tr><th>지표</th><th>단위</th><th>기준일</th><th>현재</th><th>전월</th><th>전월대비</th><th>전년</th><th>전년대비</th></tr></thead>
              <tbody>{build_market_compare_rows([scfi_row, ccfi_row])}</tbody>
            </table>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown('<div class="placeholder"><span style="font-size:26px">🚢</span><span>SCFI/CCFI 데이터를 불러올 수 없습니다</span></div>', unsafe_allow_html=True)
    st.caption("출처: 국가물류통합정보센터 국외해상운임지수 엑셀 자료. 전월/전년 값은 기준일 이전 가장 가까운 발표값 기준입니다.")
    st.markdown('</div></div>', unsafe_allow_html=True)

    v_newsales = latest(df_newsales, "신규주택판매")
    market_summary = build_market_summary(
        v_housing, d_housing, v_mortgage, d_mortgage, v_cpi, d_cpi,
        v_fedfunds, usd_krw, v_wti, d_wti
    )
    report_metrics = [
        ["Housing Starts", f"{v_housing:,.0f}K", f"{d_housing:+.1f}% MoM"],
        ["New Home Sales", f"{v_newsales:,.0f}K", "월간 발표"],
        ["Building Permits", f"{v_permits:,.0f}K", f"{d_permits:+.1f}% MoM"],
        ["Housing Completions", f"{v_complete:,.0f}K", f"{d_complete:+.1f}% MoM"],
        ["Monthly Supply", f"{v_supply:.1f}개월", f"{d_supply:+.1f}% MoM"],
        ["30Y Mortgage", f"{v_mortgage:.2f}%", f"{d_mortgage:+.2f}%p"],
        ["CPI Index", f"{v_cpi:.1f}", f"{d_cpi:+.1f}%"],
        ["Fed Funds", f"{v_fedfunds:.2f}%", "정책금리"],
        ["USD/KRW", f"{usd_krw:,.0f}", f"20거래일 {d_fx:+.1f}%"],
        ["PVC", f"{v_pvc:,.2f}", f"{d_pvc:+.1f}% MoM"],
        ["DOTP", f"{v_dotp:,.2f}", f"{d_dotp:+.1f}% MoM"],
        ["SCFI", f"{v_scfi:,.2f}", f"4주 {d_scfi:+.1f}%"],
        ["CCFI", f"{v_ccfi:,.2f}", f"4주 {d_ccfi:+.1f}%"],
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
        st.markdown('<div class="report-note">내부 보고용 1페이지 PDF와 거래선 공유용 영문 Market Brief를 각각 다운로드할 수 있습니다.</div>', unsafe_allow_html=True)
        pdf_buffer = create_pdf_report(report_metrics, market_summary, st.session_state.get("market_briefing", ""))
        st.download_button(
            "📄 1페이지 PDF 보고서 다운로드",
            data=pdf_buffer,
            file_name=f"kcc_lvt_market_brief_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        client_brief_context = {
            "usd_krw": usd_krw,
            "d_fx": d_fx,
            "housing": v_housing,
            "d_housing": d_housing,
            "newsales": v_newsales,
            "mortgage": v_mortgage,
            "d_mortgage": d_mortgage,
            "cpi": v_cpi,
            "d_cpi": d_cpi,
            "fedfunds": v_fedfunds,
            "scfi": v_scfi,
            "d_scfi": d_scfi,
            "ccfi": v_ccfi,
            "d_ccfi": d_ccfi,
            "wti": v_wti,
            "d_wti": d_wti,
            "pvc": v_pvc,
            "d_pvc": d_pvc,
            "dotp": v_dotp,
            "d_dotp": d_dotp,
        }
        client_pdf_buffer = create_client_brief_pdf(client_brief_context)
        st.download_button(
            "🇺🇸 English Client Brief PDF",
            data=client_pdf_buffer,
            file_name=f"kcc_glass_us_lvt_indicator_brief_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        monthly_freight_rows = [
            freight_compare_row("SCFI", df_freight, "SCFI"),
            freight_compare_row("CCFI", df_freight, "CCFI"),
        ]
        monthly_raw_rows = [
            purchase_compare_row("PVC", df_purchase, "PVC"),
            purchase_compare_row("DOTP", df_purchase, "DOTP"),
            indicator_compare_row("WTI", df_wti, "WTI", "$/bbl", 1),
            indicator_compare_row("Brent", df_brent, "Brent", "$/bbl", 1),
            indicator_compare_row("USD/KRW", df_fx, "USD/KRW", "KRW/USD", 0, current_override=usd_krw),
        ]
        monthly_design_items = collect_design_articles(limit=18, source_mode="FCW + FCNews")
        monthly_keyword_df = extract_design_keywords(monthly_design_items)
        monthly_implication_df = build_product_implications(monthly_keyword_df)
        monthly_pdf_buffer = create_monthly_pdf_report(
            report_metrics,
            market_summary,
            action_recs,
            alerts,
            monthly_freight_rows,
            monthly_raw_rows,
            monthly_keyword_df,
            monthly_implication_df,
            get_comment_log_df(),
        )
        st.download_button(
            "📘 월간 종합 PDF 보고서 다운로드",
            data=monthly_pdf_buffer,
            file_name=f"kcc_lvt_monthly_intelligence_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        excel_download_button(
            "📊 전체 지표 엑셀 다운로드",
            {
                "Housing": df_housing,
                "Building Permits": df_permits,
                "Housing Completions": df_complete,
                "Monthly Supply": df_month_supply,
                "Existing Home Sales": df_existing_sales,
                "Mortgage": df_mortgage,
                "New Home Sales": df_newsales,
                "Macro": df_cpi.merge(df_fedfunds, on="date", how="outer"),
                "Building Retail Sales": df_building_retail,
                "Lumber PPI": df_lumber_ppi,
                "Building Material PPI": df_building_ppi,
                "FX": df_fx,
                "Oil": df_wti.merge(df_brent, on="date", how="outer"),
                "PVC_DOTP": df_purchase[["월", "PVC", "DOTP"]],
                "Freight": df_freight,
            },
            f"kcc_lvt_all_indicators_{datetime.now().strftime('%Y%m%d')}.xlsx",
            "overview_excel_download",
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
    <div class="kpi-strip" style="grid-template-columns:repeat(5,1fr);">
      <div class="kpi"><div class="kpi-n">WTI 원유</div><div class="kpi-v">{v_wti:,.1f}<span style="font-size:12px;color:{T['text3']}">$</span></div>{chg2(d_wti)}</div>
      <div class="kpi"><div class="kpi-n">Brent 원유</div><div class="kpi-v">{v_brent:,.1f}<span style="font-size:12px;color:{T['text3']}">$</span></div>{chg2(d_brent)}</div>
      <div class="kpi"><div class="kpi-n">USD / KRW</div><div class="kpi-v">{usd_krw:,.0f}</div><div class="kpi-c fl">실시간</div></div>
      <div class="kpi"><div class="kpi-n">PVC</div><div class="kpi-v">{v_pvc:,.2f}</div>{chg2(d_pvc)}</div>
      <div class="kpi"><div class="kpi-n">DOTP</div><div class="kpi-v">{v_dotp:,.2f}</div>{chg2(d_dotp)}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">PVC / DOTP 구매팀 월별 지수</span><span class="p-m">Manual monthly update</span></div><div class="p-guide"><b>활용 포인트</b> 월별 구매팀 지수는 견적 원가 전제와 가격 조정 타이밍을 판단하는 내부 기준값으로 활용합니다.</div><div class="p-body">', unsafe_allow_html=True)
    edit_col, guide_col = st.columns([2, 1], gap="medium")
    with edit_col:
        latest_purchase = df_purchase.iloc[-1] if len(df_purchase) else {"월": datetime.now().strftime("%Y-%m"), "PVC": 0, "DOTP": 0}
        i_month, i_pvc, i_dotp = st.columns([1, 1, 1], gap="small")
        with i_month:
            input_month = st.text_input("월", value=str(latest_purchase["월"]), help="YYYY-MM 형식")
        with i_pvc:
            input_pvc = st.number_input("PVC", value=float(latest_purchase["PVC"]) if pd.notna(latest_purchase["PVC"]) else 0.0, step=0.01, format="%.2f")
        with i_dotp:
            input_dotp = st.number_input("DOTP", value=float(latest_purchase["DOTP"]) if pd.notna(latest_purchase["DOTP"]) else 0.0, step=0.01, format="%.2f")
        if st.button("월별 지수 반영", use_container_width=True, key="apply_purchase_price"):
            updated = df_purchase[["월", "PVC", "DOTP"]].copy()
            row = {
                "월": input_month[:7],
                "PVC": input_pvc if input_pvc > 0 else None,
                "DOTP": input_dotp if input_dotp > 0 else None,
            }
            if row["월"] in updated["월"].astype(str).values:
                updated.loc[updated["월"].astype(str) == row["월"], ["PVC", "DOTP"]] = [row["PVC"], row["DOTP"]]
            else:
                updated = pd.concat([updated, pd.DataFrame([row])], ignore_index=True)
            df_purchase = set_purchase_price_df(updated)
            st.rerun()
        st.markdown(dataframe_to_dark_table(df_purchase[["월", "PVC", "DOTP"]], max_rows=18), unsafe_allow_html=True)
    with guide_col:
        if st.button("기본값으로 되돌리기", use_container_width=True, key="reset_purchase_price"):
            st.session_state.purchase_price_rows = PURCHASE_PRICE_DEFAULTS
            st.rerun()
        st.markdown(
            f"""
            <div class="report-note">
            구매팀에서 월별 지수를 받으면 이 표의 마지막 행을 추가/수정하면 됩니다.<br>
            단, 웹 화면 입력값은 현재 접속 세션 기준입니다. 전체 사용자에게 고정 반영하려면 업데이트된 월별 값을 코드에 반영해 GitHub에 다시 올리는 방식이 가장 안정적입니다.
            </div>
            """,
            unsafe_allow_html=True,
        )

    dfp = df_purchase.copy()
    if len(dfp):
        fig_purchase = go.Figure()
        fig_purchase.add_trace(go.Scatter(
            x=dfp["date"], y=dfp["PVC"], name="PVC",
            mode="lines+markers", line=dict(color=T['accent'], width=2.5),
            hovertemplate="%{x|%Y-%m}<br>PVC: %{y:,.2f}<extra></extra>",
        ))
        fig_purchase.add_trace(go.Scatter(
            x=dfp["date"], y=dfp["DOTP"], name="DOTP",
            mode="lines+markers", line=dict(color=GOLD, width=2.5),
            hovertemplate="%{x|%Y-%m}<br>DOTP: %{y:,.2f}<extra></extra>",
        ))
        chart_layout(fig_purchase, 290)
        fig_purchase.update_layout(hovermode="x unified")
        st.plotly_chart(fig_purchase, use_container_width=True, config=CHART_CONFIG)

        purchase_rows = [
            purchase_compare_row("PVC", dfp, "PVC"),
            purchase_compare_row("DOTP", dfp, "DOTP"),
        ]
        st.markdown(
            f"""
            <table class="dt">
              <thead>
                <tr>
                  <th>지표</th><th>단위</th><th>기준월</th><th>현재</th>
                  <th>전월</th><th>전월대비</th><th>전년</th><th>전년대비</th>
                </tr>
              </thead>
              <tbody>{build_market_compare_rows(purchase_rows)}</tbody>
            </table>
            """,
            unsafe_allow_html=True,
        )
    st.markdown('</div></div>', unsafe_allow_html=True)

    # 기간 선택
    period = st.radio("기간", ["1년", "3년", "전체"], horizontal=True, label_visibility="collapsed", key="oil_period")
    period_map = {"1년": 365, "3년": 365*3, "전체": None}
    days = period_map[period]

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">유가 추이 (WTI / Brent)</span><span class="p-m">FRED · USD/barrel</span></div><div class="p-guide"><b>활용 포인트</b> 유가는 PVC·가소제·운임 비용 분위기에 영향을 주는 선행성 비용 신호로 봅니다.</div><div class="p-body">', unsafe_allow_html=True)
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
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
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

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">미국 자재 가격 보조 지표</span><span class="p-m">Lumber / Building Material PPI</span></div><div class="p-guide"><b>활용 포인트</b> 미국 건축 자재 전반의 가격 압력을 보며 바이어의 가격 민감도와 시장 분위기를 보조 판단합니다.</div><div class="p-body">', unsafe_allow_html=True)
    fig_aux = go.Figure()
    fig_aux.add_trace(go.Scatter(
        x=df_lumber_ppi["date"], y=df_lumber_ppi["Lumber PPI"], name="Lumber PPI",
        line=dict(color=GOLD, width=2),
        hovertemplate="%{x|%Y-%m-%d}<br>Lumber PPI: %{y:,.1f}<extra></extra>",
    ))
    fig_aux.add_trace(go.Scatter(
        x=df_building_ppi["date"], y=df_building_ppi["건자재유통PPI"], name="Building Material PPI",
        line=dict(color=T["accent"], width=2, dash="dot"),
        hovertemplate="%{x|%Y-%m-%d}<br>Building Material PPI: %{y:,.1f}<extra></extra>",
    ))
    chart_layout(fig_aux, 260)
    st.plotly_chart(fig_aux, use_container_width=True, config=CHART_CONFIG)
    st.caption("PVC/DOTP 직접 대체 지표는 아니며, 미국 건축·자재 가격 압력의 방향성을 보는 참고 지표입니다.")
    st.markdown('</div></div>', unsafe_allow_html=True)

    raw_rows = [
        raw_compare_row("WTI 원유", df_wti, "WTI", "$/bbl", 1),
        raw_compare_row("Brent 원유", df_brent, "Brent", "$/bbl", 1),
        raw_compare_row("USD/KRW", df_fx, "USD/KRW", "KRW/USD", 0, current_override=usd_krw),
        raw_compare_row("Lumber PPI", df_lumber_ppi, "Lumber PPI", "Index", 1),
        raw_compare_row("Building Material PPI", df_building_ppi, "건자재유통PPI", "Index", 1),
    ]
    raw_table = build_market_compare_rows(raw_rows)
    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">원자재 핵심 지표 비교표</span><span class="p-m">Current vs 1M / 1Y</span></div><div class="p-guide"><b>활용 포인트</b> 현재값만 보지 말고 전월·전년 대비 변화율을 같이 봐야 가격 인상/방어 논리를 만들기 쉽습니다.</div><div class="p-body">', unsafe_allow_html=True)
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
    excel_download_button(
        "📊 원자재 데이터 엑셀 다운로드",
        {
            "PVC_DOTP": df_purchase[["월", "PVC", "DOTP"]],
            "Oil": df_wti.merge(df_brent, on="date", how="outer"),
            "Lumber PPI": df_lumber_ppi,
            "Building Material PPI": df_building_ppi,
            "FX": df_fx,
        },
        f"kcc_lvt_raw_materials_{datetime.now().strftime('%Y%m%d')}.xlsx",
        "raw_material_excel_download",
    )
    st.markdown('</div></div>', unsafe_allow_html=True)
# ════════════════════════════════════════════════════════════
elif menu == "🚢 Freight":
    st.markdown('<div class="sec"><span class="sec-t">Freight & Logistics</span><span class="sec-s">운임 뉴스 · AI 위험도 분석</span></div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="kpi-strip" style="grid-template-columns:repeat(2,1fr);">
      <div class="kpi"><div class="kpi-n">SCFI</div><div class="kpi-v">{v_scfi:,.2f}</div>{kpi_change(d_scfi, "%")}</div>
      <div class="kpi"><div class="kpi-n">CCFI</div><div class="kpi-v">{v_ccfi:,.2f}</div>{kpi_change(d_ccfi, "%")}</div>
    </div>
    """, unsafe_allow_html=True)

    freight_period = st.radio("운임 지수 기간", ["1년", "전체"], horizontal=True, label_visibility="collapsed", key="freight_index_period")
    dff = df_freight.copy()
    if freight_period == "1년":
        dff = dff[dff["date"] >= (pd.Timestamp.now() - pd.Timedelta(days=365))]

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">SCFI / CCFI 추이</span><span class="p-m">국가물류통합정보센터 · Weekly</span></div><div class="p-guide"><b>활용 포인트</b> SCFI는 스팟 운임 방향성, CCFI는 계약/종합 운임 흐름을 보조적으로 읽어 선적 타이밍과 견적 유효기간을 판단합니다.</div><div class="p-body">', unsafe_allow_html=True)
    if len(dff):
        fig_ship = go.Figure()
        fig_ship.add_trace(go.Scatter(
            x=dff["date"], y=dff["SCFI"], name="SCFI",
            mode="lines+markers", line=dict(color=T['accent'], width=2.6),
            hovertemplate="%{x|%Y-%m-%d}<br>SCFI: %{y:,.2f}<extra></extra>",
        ))
        fig_ship.add_trace(go.Scatter(
            x=dff["date"], y=dff["CCFI"], name="CCFI",
            mode="lines+markers", line=dict(color=GOLD, width=2.4),
            hovertemplate="%{x|%Y-%m-%d}<br>CCFI: %{y:,.2f}<extra></extra>",
        ))
        chart_layout(fig_ship, 360)
        fig_ship.update_layout(hovermode="x unified")
        st.plotly_chart(fig_ship, use_container_width=True, config=CHART_CONFIG)
    else:
        st.markdown('<div class="placeholder"><span style="font-size:26px">🚢</span><span>운임 지수 데이터를 불러올 수 없습니다</span></div>', unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

    freight_rows = [
        freight_compare_row("SCFI", df_freight, "SCFI"),
        freight_compare_row("CCFI", df_freight, "CCFI"),
    ]
    freight_table = build_market_compare_rows(freight_rows)
    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">운임 지수 비교표</span><span class="p-m">Current vs 1M / 1Y</span></div><div class="p-body">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <table class="dt">
          <thead>
            <tr>
              <th>지표</th><th>단위</th><th>기준일</th><th>현재</th>
              <th>전월</th><th>전월대비</th><th>전년</th><th>전년대비</th>
            </tr>
          </thead>
          <tbody>{freight_table}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )
    st.caption("출처: 국가물류통합정보센터 국외해상운임지수 엑셀 자료. 전월/전년 값은 기준일 이전 가장 가까운 발표값 기준입니다.")
    excel_download_button(
        "📊 운임 지수 엑셀 다운로드",
        {"Freight": df_freight},
        f"kcc_lvt_freight_index_{datetime.now().strftime('%Y%m%d')}.xlsx",
        "freight_excel_download",
    )
    st.markdown('</div></div>', unsafe_allow_html=True)

    cN, cA = st.columns([1, 1], gap="medium")
    with cN:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">물류·운임 뉴스</span><span class="p-m">Google News RSS</span></div><div class="p-body">', unsafe_allow_html=True)
        news = llm.fetch_news("freight", limit=8)
        freight_visuals = {
            "PORT": {
                "label": "PORT",
                "badge": "PORT / TERMINAL",
                "image": "https://images.unsplash.com/photo-1586528116311-ad8dd3c8310d?auto=format&fit=crop&w=700&q=75",
            },
            "RATE": {
                "label": "RATE",
                "badge": "FREIGHT RATE",
                "image": "https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=700&q=75",
            },
            "OCEAN": {
                "label": "OCEAN",
                "badge": "OCEAN CARRIER",
                "image": "https://images.unsplash.com/photo-1578575437130-527eed3abbec?auto=format&fit=crop&w=700&q=75",
            },
            "CAPA": {
                "label": "CAPA",
                "badge": "CAPACITY",
                "image": "https://images.unsplash.com/photo-1494412651409-8963ce7935a7?auto=format&fit=crop&w=700&q=75",
            },
            "RISK": {
                "label": "RISK",
                "badge": "SUPPLY RISK",
                "image": "https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=700&q=75",
            },
        }
        def classify_freight_news(title):
            t = title.lower()
            if any(k in t for k in ["hormuz", "crisis", "blockade", "red sea", "suez", "panama", "disruption", "war", "weather", "delay", "risk", "tariff"]):
                return "RISK"
            if any(k in t for k in ["port", "terminal", "congestion", "strike", "longshore", "dockworker", "la/lb", "los angeles", "long beach"]):
                return "PORT"
            if any(k in t for k in ["capacity", "equipment", "space", "blank sailing", "blank sailings", "empty slots", "peak season", "volume", "demand", "supply", "carriers slash"]):
                return "CAPA"
            if any(k in t for k in ["ocean", "carrier", "vessel", "ship", "shipping", "sailing", "transpacific"]):
                return "OCEAN"
            if any(k in t for k in ["rate", "rates", "scfi", "ccfi", "spot", "index", "contract", "pricing"]):
                return "RATE"
            return "OCEAN"
        def freight_news_card(item, idx=0):
            title = html.escape(item.get("title", ""))
            link = html.escape(item.get("link", ""))
            published = html.escape((item.get("published", "") or "Latest")[:22])
            source = html.escape(item.get("source", "") or "Market News")
            visual_key = classify_freight_news(item.get("title", ""))
            visual = freight_visuals[visual_key]
            mark = visual["label"]
            badge = visual["badge"]
            image = visual["image"]
            bg = f"linear-gradient(135deg,rgba(14,35,114,.90),rgba(10,14,20,.42)),url('{image}')"
            klass = "freight-card featured" if idx == 0 else "freight-card"
            return (
                f'<div class="{klass}">'
                f'<div class="freight-visual" style="background-image:{bg}"><div class="freight-badge">{badge}</div><div class="freight-mark">{mark}</div></div>'
                f'<div class="freight-body">'
                f'<div class="freight-meta">{published} · {source}</div>'
                f'<a class="freight-title" href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>'
                f'<a class="freight-read" href="{link}" target="_blank" rel="noopener noreferrer">Read More &rarr;</a>'
                f'</div>'
                f'</div>'
            )
        if news:
            news_cards = "".join(freight_news_card(n, i) for i, n in enumerate(news[:6]))
            st.markdown(f'<div class="freight-stack">{news_cards}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="placeholder"><span style="font-size:26px">NEWS</span><span>뉴스를 불러올 수 없습니다</span></div>', unsafe_allow_html=True)
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
# 🎯 MARKET INSIGHT
# ════════════════════════════════════════════════════════════
elif menu == "🎯 Market Insight":
    st.markdown('<div class="sec"><span class="sec-t">Market Insight</span><span class="sec-s">미국 LVT 채널 타깃 · Distributor / Retailer / Rising Star</span></div>', unsafe_allow_html=True)

    if df_market.empty:
        st.markdown('<div class="placeholder"><span style="font-size:26px">🎯</span><span>Market Insight 데이터를 불러올 수 없습니다</span></div>', unsafe_allow_html=True)
    else:
        categories = ["Top Distributors", "Top Retailers", "Rising Stars"]
        selected_categories = st.multiselect(
            "Category",
            categories,
            default=categories,
            label_visibility="collapsed",
            key="market_categories",
        )
        market_view = df_market[df_market["category"].isin(selected_categories)].copy()
        market_view = add_opportunity_scores(market_view)

        total_companies = len(market_view)
        active_states = market_view["state"].nunique()
        sales_base_col = "sales_2025" if market_view["sales_2025"].notna().any() else "sales_2024"
        total_sales = market_view[sales_base_col].sum(skipna=True)
        avg_sales = market_view[sales_base_col].mean(skipna=True)
        priority_accounts = int((market_view["grade"] == "A").sum())
        st.markdown(f"""
        <div class="kpi-strip" style="grid-template-columns:repeat(5,1fr);">
          <div class="kpi"><div class="kpi-n">Companies</div><div class="kpi-v">{total_companies:,.0f}</div><div class="kpi-c fl">selected list</div></div>
          <div class="kpi"><div class="kpi-n">States</div><div class="kpi-v">{active_states:,.0f}</div><div class="kpi-c fl">home base coverage</div></div>
          <div class="kpi"><div class="kpi-n">Sales Base</div><div class="kpi-v">{total_sales:,.0f}<span style="font-size:12px;color:{T['text3']}">M</span></div><div class="kpi-c fl">{sales_base_col[-4]}{sales_base_col[-3:]} available</div></div>
          <div class="kpi"><div class="kpi-n">Avg Sales</div><div class="kpi-v">{avg_sales:,.1f}<span style="font-size:12px;color:{T['text3']}">M</span></div><div class="kpi-c fl">available rows</div></div>
          <div class="kpi"><div class="kpi-n">Priority A</div><div class="kpi-v">{priority_accounts:,.0f}</div><div class="kpi-c fl">opportunity score</div></div>
        </div>
        """, unsafe_allow_html=True)

        state_summary = (
            market_view.groupby("state", as_index=False)
            .agg(
                companies=("company", "count"),
                sales_2025=("sales_2025", "sum"),
                sales_2024=("sales_2024", "sum"),
            )
            .sort_values(["companies", "sales_2025", "sales_2024"], ascending=False)
        )
        state_summary["company_list"] = state_summary["state"].map(
            market_view.groupby("state")["company"].apply(lambda s: ", ".join(s.head(8))).to_dict()
        )
        state_summary["lat"] = state_summary["state"].map(lambda s: STATE_CENTERS.get(s, (None, None))[0])
        state_summary["lon"] = state_summary["state"].map(lambda s: STATE_CENTERS.get(s, (None, None))[1])
        active_state_options = state_summary["state"].dropna().sort_values().tolist()
        market_alerts = build_alerts(usd_krw, v_wti, d_wti, v_mortgage, v_scfi, d_scfi, d_pvc, d_dotp)
        customer_impact = build_customer_impact(market_view, state_summary, market_alerts)

        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Customer Impact View</span><span class="p-m">State-level exposure</span></div><div class="p-body">', unsafe_allow_html=True)
        impact_col, impact_chart_col = st.columns([1.2, 1], gap="medium")
        impact_display = customer_impact.head(10).copy()
        if not impact_display.empty:
            impact_display["영향도"] = impact_display["영향도"].map(
                lambda x: f'<span class="impact-high">{x}</span>' if x == "HIGH"
                else f'<span class="impact-mid">{x}</span>' if x == "MID"
                else f'<span class="impact-low">{x}</span>'
            )
            impact_display = impact_display[["state", "영향도", "impact_score", "companies", "priority_a", "top_accounts", "영업 포인트"]].rename(columns={
                "state": "State",
                "impact_score": "Impact Score",
                "companies": "Companies",
                "priority_a": "Priority A",
                "top_accounts": "Top Accounts",
            })
            with impact_col:
                st.markdown(dataframe_to_dark_table(impact_display), unsafe_allow_html=True)
                st.caption("영향도는 거래선 집중도, Priority A 거래선, 현재 운임/환율/금리/원가 위험 신호를 함께 반영한 참고값입니다.")
            with impact_chart_col:
                top_impact = customer_impact.head(10).sort_values("impact_score")
                fig_impact = go.Figure(go.Bar(
                    x=top_impact["impact_score"],
                    y=top_impact["state"],
                    orientation="h",
                    marker_color=GOLD,
                    hovertemplate="%{y}<br>Impact: %{x:.1f}<extra></extra>",
                ))
                chart_layout(fig_impact, 320)
                fig_impact.update_layout(xaxis_title="Impact Score", yaxis_title=None, showlegend=False)
                st.plotly_chart(fig_impact, use_container_width=True, config=CHART_CONFIG)
        else:
            st.markdown('<div class="placeholder"><span style="font-size:26px">IMPACT</span><span>영향도 계산 대상 데이터가 없습니다</span></div>', unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Account Opportunity Score</span><span class="p-m">Priority ranking</span></div><div class="p-body">', unsafe_allow_html=True)
        opp_col, opp_chart_col = st.columns([1.2, 1], gap="medium")
        top_opps = market_view.sort_values("opportunity_score", ascending=False).head(12).copy()
        top_opps["Grade"] = top_opps["grade"].map(
            lambda g: f'<span class="score-pill score-{str(g).lower()}">{g}</span>'
        )
        score_table = top_opps[["Grade", "opportunity_score", "category", "company", "state", "sales_base"]].rename(columns={
            "opportunity_score": "Score",
            "category": "Category",
            "company": "Company",
            "state": "State",
            "sales_base": "Sales Base",
        })
        with opp_col:
            st.markdown(dataframe_to_dark_table(score_table), unsafe_allow_html=True)
            st.caption("점수는 매출 규모, 순위, 주별 집중도, 성장률, 카테고리 가중치를 합산한 우선순위 참고값입니다.")
        with opp_chart_col:
            fig_opp = go.Figure(go.Bar(
                x=top_opps.sort_values("opportunity_score")["opportunity_score"],
                y=top_opps.sort_values("opportunity_score")["company"],
                orientation="h",
                marker_color=T["accent"],
                hovertemplate="%{y}<br>Score: %{x:.1f}<extra></extra>",
            ))
            chart_layout(fig_opp, 320)
            fig_opp.update_layout(xaxis_title="Opportunity Score", yaxis_title=None, showlegend=False)
            st.plotly_chart(fig_opp, use_container_width=True, config=CHART_CONFIG)
        st.markdown('</div></div>', unsafe_allow_html=True)

        map_col, bar_col = st.columns([2, 1], gap="medium")
        with map_col:
            st.markdown('<div class="panel"><div class="p-head"><span class="p-t">US Channel Footprint</span><span class="p-m">Company count by state</span></div><div class="p-body">', unsafe_allow_html=True)
            selected_state = st.selectbox(
                "State Focus",
                ["All States"] + active_state_options,
                key="market_state_focus",
            )
            labels_df = state_summary.dropna(subset=["lat", "lon"]).copy()
            fig_map = go.Figure(data=go.Choropleth(
                locations=state_summary["state"],
                z=state_summary["companies"],
                locationmode="USA-states",
                colorscale=[[0, "#162033"], [0.5, "#2D7FF9"], [1, "#E8B339"]],
                marker_line_color=T["border"],
                colorbar=dict(title="Count"),
                customdata=state_summary[["sales_2025", "sales_2024", "company_list"]],
                hovertemplate=(
                    "<b>%{location}</b><br>"
                    "Companies: %{z}<br>"
                    "2025 Sales: %{customdata[0]:,.1f}M<br>"
                    "2024 Sales: %{customdata[1]:,.1f}M<br>"
                    "%{customdata[2]}<extra></extra>"
                ),
            ))
            fig_map.add_trace(go.Scattergeo(
                lon=labels_df["lon"],
                lat=labels_df["lat"],
                text=labels_df["state"],
                mode="text",
                textfont=dict(color="#FFFFFF", size=fs(10), family="Arial Black"),
                hoverinfo="skip",
                showlegend=False,
            ))
            if selected_state != "All States":
                selected_row = state_summary[state_summary["state"] == selected_state]
                if len(selected_row):
                    fig_map.add_trace(go.Choropleth(
                        locations=selected_row["state"],
                        z=selected_row["companies"],
                        locationmode="USA-states",
                        colorscale=[[0, "#E8B339"], [1, "#E8B339"]],
                        showscale=False,
                        marker_line_color="#FFFFFF",
                        marker_line_width=2.5,
                        hovertemplate=(
                            "<b>%{location}</b><br>"
                            "Focused state<br>"
                            "Companies: %{z}<extra></extra>"
                        ),
                    ))
                    lat = float(selected_row["lat"].iloc[0])
                    lon = float(selected_row["lon"].iloc[0])
                    fig_map.update_geos(
                        scope="usa",
                        center=dict(lat=lat, lon=lon),
                        projection_scale=4.2,
                        bgcolor="rgba(0,0,0,0)",
                        lakecolor="rgba(0,0,0,0)",
                        landcolor=T["panel2"],
                    )
                else:
                    fig_map.update_geos(scope="usa", bgcolor="rgba(0,0,0,0)", lakecolor="rgba(0,0,0,0)", landcolor=T["panel2"])
            else:
                fig_map.update_geos(scope="usa", bgcolor="rgba(0,0,0,0)", lakecolor="rgba(0,0,0,0)", landcolor=T["panel2"])
            chart_layout(fig_map, 390)
            fig_map.update_layout(margin=dict(l=0, r=0, t=0, b=0))
            st.plotly_chart(fig_map, use_container_width=True, config=CHART_CONFIG)
            st.markdown('</div></div>', unsafe_allow_html=True)

        with bar_col:
            if selected_state == "All States":
                st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Top States</span><span class="p-m">Concentration</span></div><div class="p-body">', unsafe_allow_html=True)
                top_states = state_summary.head(10).sort_values("companies")
                fig_state = go.Figure(go.Bar(
                    x=top_states["companies"],
                    y=top_states["state"],
                    orientation="h",
                    marker_color=T["accent"],
                    hovertemplate="%{y}<br>Companies: %{x}<extra></extra>",
                ))
                chart_layout(fig_state, 390)
                fig_state.update_layout(xaxis_title=None, yaxis_title=None, showlegend=False)
                st.plotly_chart(fig_state, use_container_width=True, config=CHART_CONFIG)
            else:
                focused_accounts = market_view[market_view["state"] == selected_state].copy()
                st.markdown(f'<div class="panel"><div class="p-head"><span class="p-t">{selected_state} Accounts</span><span class="p-m">{len(focused_accounts)} companies</span></div><div class="p-body">', unsafe_allow_html=True)
                if len(focused_accounts):
                    focused_cols = ["grade", "opportunity_score", "category", "company", "home_base", "sales_2025", "sales_2024"]
                    focused_table = focused_accounts[focused_cols].sort_values(
                        ["opportunity_score", "category", "sales_2025", "sales_2024"],
                        ascending=[False, True, False, False],
                        na_position="last",
                    )
                    focused_table = focused_table.rename(columns={"grade": "Grade", "opportunity_score": "Score"})
                    st.markdown(dataframe_to_dark_table(focused_table), unsafe_allow_html=True)
                else:
                    st.markdown('<div class="placeholder"><span style="font-size:26px">🎯</span><span>선택한 주의 거래선이 없습니다</span></div>', unsafe_allow_html=True)
            st.markdown('</div></div>', unsafe_allow_html=True)

        mix_col, sales_col = st.columns([1, 1], gap="medium")
        with mix_col:
            st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Channel Mix</span><span class="p-m">List composition</span></div><div class="p-body">', unsafe_allow_html=True)
            mix = market_view.groupby("category", as_index=False).agg(companies=("company", "count"))
            fig_mix = go.Figure(go.Pie(
                labels=mix["category"],
                values=mix["companies"],
                hole=0.55,
                marker=dict(colors=[T["accent"], GOLD, T["up"]]),
                hovertemplate="%{label}<br>Companies: %{value}<br>%{percent}<extra></extra>",
            ))
            chart_layout(fig_mix, 260)
            st.plotly_chart(fig_mix, use_container_width=True, config=CHART_CONFIG)
            st.markdown('</div></div>', unsafe_allow_html=True)

        with sales_col:
            st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Largest Accounts</span><span class="p-m">Sales base</span></div><div class="p-body">', unsafe_allow_html=True)
            sales_col_name = "sales_2025" if market_view["sales_2025"].notna().any() else "sales_2024"
            top_sales = market_view.dropna(subset=[sales_col_name]).nlargest(10, sales_col_name).sort_values(sales_col_name)
            fig_sales = go.Figure(go.Bar(
                x=top_sales[sales_col_name],
                y=top_sales["company"],
                orientation="h",
                marker_color=GOLD,
                hovertemplate="%{y}<br>Sales: %{x:,.1f}M<extra></extra>",
            ))
            chart_layout(fig_sales, 260)
            fig_sales.update_layout(xaxis_title="USD millions", yaxis_title=None, showlegend=False)
            st.plotly_chart(fig_sales, use_container_width=True, config=CHART_CONFIG)
            st.markdown('</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Target Account Table</span><span class="p-m">Filter-ready list</span></div><div class="p-body">', unsafe_allow_html=True)
        display_cols = [
            "grade", "opportunity_score", "category", "type", "rank_2025", "rank_2024", "rank_2023", "rank_2022",
            "company", "home_base", "state", "sales_2025", "sales_2024", "sales_2023", "sales_2022"
        ]
        account_table = market_view[display_cols].sort_values(["opportunity_score", "category", "rank_2025", "rank_2024", "company"], ascending=[False, True, True, True, True], na_position="last")
        st.markdown(dataframe_to_dark_table(account_table), unsafe_allow_html=True)
        excel_download_button(
            "📊 Market Insight 엑셀 다운로드",
            {
                "Accounts": market_view[display_cols],
                "State Summary": state_summary,
                "Opportunity Top": top_opps[["grade", "opportunity_score", "category", "company", "home_base", "state", "sales_base"]],
                "Customer Impact": customer_impact,
            },
            f"kcc_lvt_market_insight_{datetime.now().strftime('%Y%m%d')}.xlsx",
            "market_insight_excel_download",
        )
        st.caption("현재 데이터는 제공된 캡처에서 확인 가능한 항목 기준입니다. 원본 엑셀을 주면 순위와 매출값을 더 정확하게 정리할 수 있습니다.")
        st.markdown('</div></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 🗺 ACCOUNT MAP
# ════════════════════════════════════════════════════════════
elif menu == "🗺 Account Map":
    st.markdown('<div class="sec"><span class="sec-t">North America Account Map</span><span class="sec-s">미국·캐나다 LVT / 바닥재 거래선 지도 · Searchable lead view</span><span class="live"><span class="dot"></span>Session ready</span></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="co-note">기본값은 Market Insight 거래선과 현재 세션의 ImportYeti 업로드 데이터를 합친 지도입니다. 별도 거래선 엑셀을 올리면 현재 세션에만 추가되고, GitHub/배포 파일에는 저장되지 않습니다.</div>',
        unsafe_allow_html=True,
    )

    with st.expander("Google Places Lead Finder — 구글맵 기반 후보 업체 자동 발굴", expanded=False):
        key_status = "연결 준비 완료" if google_places_key else "GOOGLE_PLACES_API_KEY 필요"
        st.caption(f"상태: {key_status}. 검색 결과는 현재 세션에만 추가됩니다. 기본 필드는 업체명, 주소, 좌표, 구글맵 링크 중심으로 제한했습니다.")
        gp1, gp2, gp3, gp4 = st.columns([1.15, 1, 1, 0.8], gap="small")
        with gp1:
            keyword_choice = st.selectbox(
                "검색 키워드",
                [
                    "flooring distributor",
                    "flooring retailer",
                    "floor covering store",
                    "vinyl flooring distributor",
                    "LVT flooring",
                    "commercial flooring contractor",
                    "custom",
                ],
                key="places_keyword_choice",
            )
            if keyword_choice == "custom":
                keyword = st.text_input("Custom keyword", value="LVT flooring distributor", key="places_keyword_custom")
            else:
                keyword = keyword_choice
        with gp2:
            place_country = st.selectbox("국가", ["United States", "Canada"], key="places_country")
            region_pool = US_STATE_CODES if place_country == "United States" else CA_PROVINCE_CODES
            region_choice = st.selectbox(
                "State / Province",
                ["전체"] + sorted(region_pool),
                format_func=lambda x: "전체" if x == "전체" else f"{x} · {REGION_NAMES.get(x, x)}",
                key="places_region",
            )
        with gp3:
            city_query = st.text_input("도시 optional", placeholder="예: Dallas, Toronto", key="places_city")
            max_results = st.slider("최대 결과", 5, 20, 10, 5, key="places_max_results")
        with gp4:
            include_contact = st.checkbox("전화/웹/평점 포함", value=False, key="places_include_contact")
            st.caption("선택 시 Google 과금 필드가 늘 수 있습니다.")

        location_query = place_country
        if region_choice != "전체":
            location_query = f"{REGION_NAMES.get(region_choice, region_choice)} {place_country}"
        if city_query.strip():
            location_query = f"{city_query.strip()} {location_query}"
        text_query = f"{keyword} in {location_query}"
        st.markdown(f'<span class="account-chip">Query · {html.escape(text_query)}</span>', unsafe_allow_html=True)
        gpb1, gpb2 = st.columns([1, 1], gap="small")
        with gpb1:
            if st.button("Google Places에서 후보 불러오기", use_container_width=True, key="places_search_btn"):
                if not google_places_key:
                    st.error("Streamlit Secrets에 GOOGLE_PLACES_API_KEY를 먼저 넣어주세요.")
                else:
                    try:
                        places_df = google_places_text_search(
                            google_places_key,
                            text_query,
                            "Google Places Lead",
                            max_results=max_results,
                            include_contact_fields=include_contact,
                        )
                        existing = get_google_places_account_df()
                        merged = pd.concat([existing, places_df], ignore_index=True)
                        merged = merged.drop_duplicates(subset=["company", "home_base"], keep="first")
                        st.session_state.google_places_rows = merged.to_dict("records")
                        st.success(f"검색 완료: 신규/기존 포함 {len(merged):,}개 Google Places 후보가 현재 지도에 반영되었습니다.")
                    except Exception as e:
                        st.error(f"Google Places 검색 실패: {e}")
        with gpb2:
            if st.session_state.get("google_places_rows") and st.button("Google Places 후보 초기화", use_container_width=True, key="places_reset_btn"):
                st.session_state.google_places_rows = []
                st.rerun()

    with st.expander("Account Excel Upload Center — 거래선 후보 리스트 추가", expanded=False):
        st.caption("권장 컬럼: company, category, country, state/province, city, home_base/address, website, notes, lat, lon. 위도/경도가 없으면 주/Province 중심에 자동 배치합니다.")
        account_upload = st.file_uploader("거래선 엑셀 업로드", type=["xlsx", "xls"], key="account_map_upload")
        if account_upload is not None:
            account_sig = f"{account_upload.name}:{getattr(account_upload, 'size', 0)}"
            if st.session_state.get("account_upload_signature") != account_sig:
                try:
                    uploaded_accounts = normalize_account_upload(account_upload)
                    st.session_state.account_map_rows = uploaded_accounts.to_dict("records")
                    st.session_state.account_upload_signature = account_sig
                    st.success(f"업로드 완료: {len(uploaded_accounts):,}개 거래선 후보를 현재 세션 지도에 반영했습니다.")
                except Exception as e:
                    st.error(f"업로드 실패: {e}")
            elif st.session_state.get("account_map_rows"):
                st.success("이미 반영된 파일입니다. 지도와 테이블에 업로드 거래선이 포함되어 있습니다.")
        if st.session_state.get("account_map_rows"):
            if st.button("업로드 거래선 초기화", use_container_width=True, key="account_upload_reset"):
                st.session_state.account_map_rows = []
                st.session_state.account_upload_signature = ""
                st.rerun()

    account_df = build_account_map_df(df_market, get_competitor_destination_df())
    if account_df.empty:
        st.markdown('<div class="placeholder"><span style="font-size:26px">🗺</span><span>표시할 거래선 데이터가 없습니다</span></div>', unsafe_allow_html=True)
    else:
        a1, a2, a3, a4 = st.columns([1.15, 1, 1, 1], gap="small")
        with a1:
            search_text = st.text_input("Search", placeholder="업체명, 도시, 메모 검색", key="account_search")
        with a2:
            source_opts = sorted(account_df["source"].dropna().unique().tolist())
            selected_sources = st.multiselect("Source", source_opts, default=source_opts, key="account_source_filter")
        with a3:
            category_opts = sorted(account_df["category"].dropna().unique().tolist())
            selected_account_categories = st.multiselect("Category", category_opts, default=category_opts, key="account_category_filter")
        with a4:
            country_opts = sorted(account_df["country"].dropna().unique().tolist())
            selected_countries = st.multiselect("Country", country_opts, default=country_opts, key="account_country_filter")

        filtered = account_df[
            account_df["source"].isin(selected_sources)
            & account_df["category"].isin(selected_account_categories)
            & account_df["country"].isin(selected_countries)
        ].copy()
        if search_text.strip():
            q = search_text.strip().lower()
            search_blob = (
                filtered["company"].astype(str) + " " +
                filtered["city"].astype(str) + " " +
                filtered["home_base"].astype(str) + " " +
                filtered["notes"].astype(str) + " " +
                filtered["state"].astype(str)
            ).str.lower()
            filtered = filtered[search_blob.str.contains(re.escape(q), na=False)].copy()

        region_options = ["All Regions"] + sorted([r for r in filtered["state"].dropna().unique().tolist() if r])
        focused_region = st.selectbox("State / Province Focus", region_options, key="account_region_focus")
        if focused_region != "All Regions":
            filtered = filtered[filtered["state"] == focused_region].copy()

        mapped = filtered.dropna(subset=["lat", "lon"]).copy()
        region_summary = (
            filtered.groupby(["country", "state"], as_index=False)
            .agg(accounts=("company", "count"), sales=("sales", "sum"))
            .sort_values(["accounts", "sales"], ascending=False)
        )
        total_accounts = len(filtered)
        mapped_regions = filtered["state"].replace("", pd.NA).dropna().nunique()
        market_accounts = int((filtered["source"] == "Market Insight").sum())
        upload_accounts = int((filtered["source"] == "Uploaded Excel").sum())
        importyeti_accounts = int((filtered["source"] == "ImportYeti Upload").sum())
        google_accounts = int((filtered["source"] == "Google Places").sum())
        st.markdown(f"""
        <div class="account-source-grid">
          <div class="account-source"><div class="account-k">Visible Accounts</div><div class="account-v">{total_accounts:,.0f}</div><div class="account-c">현재 검색/필터 기준</div></div>
          <div class="account-source"><div class="account-k">Regions</div><div class="account-v">{mapped_regions:,.0f}</div><div class="account-c">State / Province coverage</div></div>
          <div class="account-source"><div class="account-k">Core List</div><div class="account-v">{market_accounts:,.0f}</div><div class="account-c">Market Insight 기반 거래선</div></div>
          <div class="account-source"><div class="account-k">Session Leads</div><div class="account-v">{upload_accounts + importyeti_accounts + google_accounts:,.0f}</div><div class="account-c">엑셀/ImportYeti/Google 후보</div></div>
        </div>
        """, unsafe_allow_html=True)

        map_col, focus_col = st.columns([1.7, 1], gap="medium")
        with map_col:
            st.markdown('<div class="panel"><div class="p-head"><span class="p-t">US / Canada Account Footprint</span><span class="p-m">Pins by account · hover for detail</span></div><div class="p-guide"><b>활용 포인트</b> 주별 거래선 밀집도와 Google/ImportYeti 후보를 함께 보며 영업 타깃 지역과 방문 우선순위를 잡습니다.</div><div class="p-body">', unsafe_allow_html=True)
            map_view_mode = st.radio(
                "Map View",
                ["3D Perspective", "2D Region Map"],
                horizontal=True,
                label_visibility="collapsed",
                key="account_map_view_mode",
            )
            if mapped.empty:
                st.markdown('<div class="placeholder"><span style="font-size:26px">📍</span><span>좌표로 배치 가능한 거래선이 없습니다</span></div>', unsafe_allow_html=True)
            else:
                category_colors = {
                    "Top Distributors": T["accent"],
                    "Top Retailers": GOLD,
                    "Rising Stars": T["up"],
                    "ImportYeti Lead": T["down"],
                    "Google Places Lead": "#A78BFA",
                    "Uploaded Lead": "#A78BFA",
                }
                label_regions = region_summary[region_summary["state"].isin(REGION_CENTERS.keys())].copy()
                if not label_regions.empty:
                    label_regions["lat"] = label_regions["state"].map(lambda s: REGION_CENTERS.get(s, (None, None))[0])
                    label_regions["lon"] = label_regions["state"].map(lambda s: REGION_CENTERS.get(s, (None, None))[1])

                if map_view_mode == "3D Perspective":
                    fig_accounts = go.Figure()
                    for cat in sorted(mapped["category"].dropna().unique()):
                        sub = mapped[mapped["category"] == cat].copy()
                        size_base = pd.to_numeric(sub["sales"], errors="coerce").fillna(0)
                        size = (size_base.rank(pct=True).fillna(0.4) * 16 + 9).clip(10, 28)
                        fig_accounts.add_trace(go.Scattermapbox(
                            lon=sub["lon"],
                            lat=sub["lat"],
                            mode="markers",
                            name=str(cat),
                            text=sub["company"],
                            customdata=sub[["source", "country", "state", "home_base", "sales", "notes"]],
                            marker=dict(
                                size=size,
                                color=category_colors.get(cat, "#7AA7FF"),
                                opacity=0.88,
                            ),
                            hovertemplate=(
                                "<b>%{text}</b><br>"
                                "%{customdata[0]} · %{customdata[1]} %{customdata[2]}<br>"
                                "%{customdata[3]}<br>"
                                "Scale: %{customdata[4]:,.0f}<br>"
                                "%{customdata[5]}<extra></extra>"
                            ),
                        ))
                    if not label_regions.empty:
                        fig_accounts.add_trace(go.Scattermapbox(
                            lon=label_regions["lon"],
                            lat=label_regions["lat"],
                            text=label_regions["state"] + " · " + label_regions["accounts"].astype(str),
                            mode="text",
                            textfont=dict(color="#FFFFFF" if st.session_state.theme == "dark" else "#0F1722", size=fs(10), family="Arial Black"),
                            hoverinfo="skip",
                            showlegend=False,
                        ))
                    if focused_region != "All Regions" and focused_region in REGION_CENTERS:
                        center_lat, center_lon = REGION_CENTERS[focused_region]
                        zoom = 5.25
                    else:
                        center_lat, center_lon, zoom = 43.5, -96.0, 2.85
                    mapbox_style = "carto-darkmatter" if st.session_state.theme == "dark" else "carto-positron"
                    fig_accounts.update_layout(
                        paper_bgcolor='rgba(0,0,0,0)',
                        plot_bgcolor='rgba(0,0,0,0)',
                        font=dict(color=T['text2'], size=11),
                        margin=dict(l=0, r=0, t=0, b=0),
                        height=560,
                        mapbox=dict(
                            style=mapbox_style,
                            center=dict(lat=center_lat, lon=center_lon),
                            zoom=zoom,
                            pitch=48,
                            bearing=-18,
                        ),
                        legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01, bgcolor="rgba(0,0,0,0.18)"),
                        hoverlabel=dict(bgcolor=T['panel2'], bordercolor=T['accent'], font=dict(color=T['text'], size=fs(12))),
                    )
                else:
                    fig_accounts = go.Figure()
                    for cat in sorted(mapped["category"].dropna().unique()):
                        sub = mapped[mapped["category"] == cat].copy()
                        size_base = pd.to_numeric(sub["sales"], errors="coerce").fillna(0)
                        size = (size_base.rank(pct=True).fillna(0.4) * 16 + 7).clip(8, 24)
                        fig_accounts.add_trace(go.Scattergeo(
                            lon=sub["lon"],
                            lat=sub["lat"],
                            mode="markers",
                            name=str(cat),
                            text=sub["company"],
                            customdata=sub[["source", "country", "state", "home_base", "sales", "notes"]],
                            marker=dict(
                                size=size,
                                color=category_colors.get(cat, "#7AA7FF"),
                                opacity=0.82,
                                line=dict(color="#FFFFFF", width=0.8),
                            ),
                            hovertemplate=(
                                "<b>%{text}</b><br>"
                                "%{customdata[0]} · %{customdata[1]} %{customdata[2]}<br>"
                                "%{customdata[3]}<br>"
                                "Scale: %{customdata[4]:,.0f}<br>"
                                "%{customdata[5]}<extra></extra>"
                            ),
                        ))
                    if not label_regions.empty:
                        fig_accounts.add_trace(go.Scattergeo(
                            lon=label_regions["lon"],
                            lat=label_regions["lat"],
                            text=label_regions["state"] + " · " + label_regions["accounts"].astype(str),
                            mode="text",
                            textfont=dict(color="#FFFFFF", size=fs(9), family="Arial Black"),
                            hoverinfo="skip",
                            showlegend=False,
                        ))
                    geo_kwargs = dict(
                        scope="north america",
                        projection_type="mercator",
                        bgcolor="rgba(0,0,0,0)",
                        landcolor=T["panel2"],
                        lakecolor=T["bg"],
                        oceancolor=T["bg"],
                        showcountries=True,
                        countrycolor=T["border"],
                        showsubunits=True,
                        subunitcolor=T["border"],
                        showocean=True,
                    )
                    if focused_region != "All Regions" and focused_region in REGION_CENTERS:
                        lat, lon = REGION_CENTERS[focused_region]
                        geo_kwargs.update(center=dict(lat=lat, lon=lon), projection_scale=4.6)
                    else:
                        geo_kwargs.update(center=dict(lat=44, lon=-98), projection_scale=1.45)
                    fig_accounts.update_geos(**geo_kwargs)
                    chart_layout(fig_accounts, 560)
                    fig_accounts.update_layout(
                        margin=dict(l=0, r=0, t=0, b=0),
                        legend=dict(orientation="h", yanchor="bottom", y=0.01, xanchor="left", x=0.01, bgcolor="rgba(0,0,0,0.15)"),
                        hovermode="closest",
                    )
                st.plotly_chart(fig_accounts, use_container_width=True, config=CHART_CONFIG)
            st.markdown('</div></div>', unsafe_allow_html=True)

        with focus_col:
            if focused_region == "All Regions":
                st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Top Regions</span><span class="p-m">Account concentration</span></div><div class="p-body">', unsafe_allow_html=True)
                top_regions = region_summary.head(14).copy()
                if not top_regions.empty:
                    top_regions["Region"] = top_regions["country"].str.replace("United States", "US", regex=False).str.replace("Canada", "CA", regex=False) + " · " + top_regions["state"]
                    fig_region = go.Figure(go.Bar(
                        x=top_regions.sort_values("accounts")["accounts"],
                        y=top_regions.sort_values("accounts")["Region"],
                        orientation="h",
                        marker_color=GOLD,
                        hovertemplate="%{y}<br>Accounts: %{x}<extra></extra>",
                    ))
                    chart_layout(fig_region, 330)
                    fig_region.update_layout(xaxis_title=None, yaxis_title=None, showlegend=False)
                    st.plotly_chart(fig_region, use_container_width=True, config=CHART_CONFIG)
                st.markdown('</div></div>', unsafe_allow_html=True)
                st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Map Sources</span><span class="p-m">Data mix</span></div><div class="p-body">', unsafe_allow_html=True)
                for src, cnt in filtered["source"].value_counts().items():
                    st.markdown(f'<span class="account-chip">{html.escape(str(src))} · {cnt:,}</span>', unsafe_allow_html=True)
                st.markdown('</div></div>', unsafe_allow_html=True)
            else:
                region_accounts = filtered.sort_values(["sales", "company"], ascending=[False, True]).copy()
                st.markdown(f'<div class="panel"><div class="p-head"><span class="p-t">{focused_region} Account List</span><span class="p-m">{len(region_accounts)} accounts</span></div><div class="p-body">', unsafe_allow_html=True)
                display_region = region_accounts[["source", "category", "company", "home_base", "sales", "notes"]].rename(columns={
                    "source": "Source", "category": "Category", "company": "Company", "home_base": "Location", "sales": "Scale", "notes": "Notes"
                })
                st.markdown(dataframe_to_dark_table(display_region, max_rows=18), unsafe_allow_html=True)
                st.markdown('</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Searchable Account Table</span><span class="p-m">Filtered result</span></div><div class="p-body">', unsafe_allow_html=True)
        table_df = filtered.copy()
        table_df["Website"] = table_df["website"].apply(
            lambda url: f'<a href="{html.escape(str(url))}" target="_blank" rel="noopener noreferrer">Open</a>'
            if str(url).strip() and str(url).lower() != "nan" else ""
        )
        table_df = table_df[["source", "category", "type", "country", "state", "company", "home_base", "Website", "sales", "priority", "notes"]].rename(columns={
            "source": "Source", "category": "Category", "type": "Type", "country": "Country", "state": "State/Province",
            "company": "Company", "home_base": "Location", "sales": "Scale", "priority": "Priority", "notes": "Notes",
        })
        table_df = table_df.sort_values(["Country", "State/Province", "Category", "Scale", "Company"], ascending=[True, True, True, False, True])
        st.markdown(dataframe_to_dark_table(table_df), unsafe_allow_html=True)
        excel_download_button(
            "📊 Account Map 엑셀 다운로드",
            {
                "Filtered Accounts": table_df.drop(columns=["Website"], errors="ignore"),
                "Region Summary": region_summary,
                "Raw Account Map": filtered,
            },
            f"kcc_lvt_account_map_{datetime.now().strftime('%Y%m%d')}.xlsx",
            "account_map_excel_download",
        )
        st.caption("현재 핀은 주/Province 중심 좌표 기반입니다. 엑셀에 lat/lon 컬럼을 추가하면 개별 주소 수준의 정확한 위치로 표시할 수 있습니다.")
        st.markdown('</div></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 🏭 COMPETITOR EXPORT
# ════════════════════════════════════════════════════════════
elif menu == "🏭 Competitor Export":
    st.markdown('<div class="sec"><span class="sec-t">Competitor Export Tracker</span><span class="sec-s">ImportYeti · B/L Weight 기준 국내 경쟁사 미국 수출동향 추정</span><span class="live"><span class="dot"></span>Session only</span></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="co-note">이 화면은 ImportYeti 원본 엑셀을 업로드한 현재 세션에서만 분석됩니다. 원본 데이터는 GitHub/코드에 저장하지 않으며, B/L Weight 기준이므로 매출액이나 실제 시장점유율이 아닌 방향성 추정치로 보는 것이 안전합니다.</div>',
        unsafe_allow_html=True,
    )

    with st.expander("ImportYeti Excel Upload Center — 원본 파일 업로드", expanded=("competitor_export_rows" not in st.session_state)):
        uploaded_competitor = st.file_uploader("ImportYeti raw 엑셀 업로드", type=["xlsx", "xls"], key="competitor_export_upload")
        if uploaded_competitor is not None:
            upload_signature = f"{uploaded_competitor.name}:{getattr(uploaded_competitor, 'size', 0)}"
            if st.session_state.get("competitor_upload_signature") != upload_signature:
                try:
                    monthly_df, detail_df, product_df = normalize_importyeti_raw_upload(uploaded_competitor)
                    set_competitor_export_data(monthly_df, detail_df, product_df)
                    st.session_state.competitor_upload_signature = upload_signature
                    st.session_state.competitor_upload_status = {
                        "file": uploaded_competitor.name,
                        "mode": "ImportYeti raw",
                        "months": f"{monthly_df['month'].min()} ~ {monthly_df['month'].max()}",
                        "competitors": int(monthly_df["competitor"].nunique()),
                        "monthly_rows": int(len(monthly_df)),
                        "detail_rows": int(len(detail_df)),
                        "weight": float(monthly_df["weight_kg"].sum()),
                        "time": datetime.now().strftime("%H:%M:%S"),
                    }
                    st.success("업로드 완료: ImportYeti raw 데이터를 현재 세션에 반영했습니다.")
                except Exception as e:
                    try:
                        uploaded_competitor.seek(0)
                        uploaded_df = normalize_competitor_upload(uploaded_competitor)
                        set_competitor_export_df(uploaded_df)
                        st.session_state.competitor_upload_signature = upload_signature
                        st.session_state.competitor_upload_status = {
                            "file": uploaded_competitor.name,
                            "mode": "Pivot monthly",
                            "months": f"{uploaded_df['month'].min()} ~ {uploaded_df['month'].max()}",
                            "competitors": int(uploaded_df["competitor"].nunique()),
                            "monthly_rows": int(len(uploaded_df)),
                            "detail_rows": 0,
                            "weight": float(uploaded_df["weight_kg"].sum()),
                            "time": datetime.now().strftime("%H:%M:%S"),
                        }
                        st.success("업로드 완료: 피벗형 월별 Weight 데이터를 현재 세션에 반영했습니다.")
                    except Exception as e2:
                        st.error(f"업로드 파일 구조를 확인해주세요. Raw 오류: {e} / Pivot 오류: {e2}")
            else:
                st.info("이미 반영된 파일입니다. 아래 대시보드에 업로드 데이터가 표시됩니다.")
        if "competitor_export_rows" in st.session_state:
            if st.button("업로드 데이터 초기화", use_container_width=True, key="clear_competitor_upload"):
                for key in [
                    "competitor_export_rows", "competitor_destination_rows", "competitor_product_rows",
                    "competitor_upload_signature", "competitor_upload_status",
                ]:
                    st.session_state.pop(key, None)
                st.success("업로드 데이터를 초기화했습니다. 새 파일을 다시 업로드해주세요.")
                st.rerun()
        st.caption("Raw 권장 컬럼: date, company, weight, supplier, route, product_description. 업로드 데이터는 현재 세션에서만 분석되며 GitHub/코드에 저장되지 않습니다.")

    upload_status = st.session_state.get("competitor_upload_status")
    if upload_status:
        st.markdown(
            f"""
            <div class="upload-done">
              <div class="upload-done-t">업로드 반영 완료</div>
              <div class="upload-done-d">
                파일: {html.escape(upload_status.get("file", ""))} · 형식: {html.escape(upload_status.get("mode", ""))} ·
                기간: {html.escape(str(upload_status.get("months", "")))} · 경쟁사 {upload_status.get("competitors", 0):,.0f}개 ·
                월별 집계 {upload_status.get("monthly_rows", 0):,.0f}행 · 상세 집계 {upload_status.get("detail_rows", 0):,.0f}행 ·
                총 Weight {upload_status.get("weight", 0):,.0f} kg · 반영시각 {html.escape(upload_status.get("time", ""))}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    df_comp = get_competitor_export_df()
    if df_comp.empty:
        st.markdown(
            """
            <div class="upload-wait">
              <div class="upload-wait-icon">📤</div>
              <div class="upload-wait-t">ImportYeti 원본 엑셀을 업로드하면 분석이 시작됩니다</div>
              <div class="upload-wait-d">
                업로드 전에는 경쟁사 수출동향 데이터를 표시하지 않습니다. 파일을 넣으면 월별 Weight, 경쟁사별 비중,
                수입자/도착지 상세, 제품 설명 집계가 같은 화면에 자동 반영됩니다.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.stop()
    df_dest = get_competitor_destination_df()
    df_product = get_competitor_product_df()
    months = sorted(df_comp["month"].dropna().unique().tolist())
    competitors = sorted(df_comp["competitor"].dropna().unique().tolist())
    f1, f2 = st.columns([1.2, 1], gap="medium")
    with f1:
        selected_competitors = st.multiselect(
            "Competitors",
            competitors,
            default=competitors,
            label_visibility="collapsed",
            key="competitor_export_filter",
        )
    with f2:
        selected_months = st.multiselect(
            "Period",
            months,
            default=months[-13:] if len(months) > 13 else months,
            label_visibility="collapsed",
            key="competitor_export_period",
        )
    if not selected_competitors:
        selected_competitors = competitors
    if not selected_months:
        selected_months = months

    view = df_comp[df_comp["competitor"].isin(selected_competitors) & df_comp["month"].isin(selected_months)].copy()
    dest_view = df_dest[df_dest["competitor"].isin(selected_competitors)].copy()
    product_view = df_product[df_product["competitor"].isin(selected_competitors)].copy() if not df_product.empty else df_product.copy()
    data_mode = "Uploaded raw" if "competitor_export_rows" in st.session_state else "Demo data"
    total_weight = view["weight_kg"].sum()
    total_shipments = view["shipments"].sum() if "shipments" in view.columns else 0
    latest_month = max(selected_months) if selected_months else ""
    latest_total = view[view["month"] == latest_month]["weight_kg"].sum() if latest_month else 0
    top_summary = view.groupby("competitor", as_index=False)["weight_kg"].sum().sort_values("weight_kg", ascending=False)
    top_name = top_summary.iloc[0]["competitor"] if len(top_summary) else "N/A"
    top_weight = top_summary.iloc[0]["weight_kg"] if len(top_summary) else 0
    dest_top = dest_view.sort_values("weight_kg", ascending=False).iloc[0]["importer"] if len(dest_view) else "N/A"

    st.markdown(f"""
    <div class="kpi-strip" style="grid-template-columns:repeat(4,1fr);">
      <div class="kpi"><div class="kpi-n">Total B/L Weight</div><div class="kpi-v">{total_weight:,.0f}</div><div class="kpi-c fl">kg · selected period</div></div>
      <div class="kpi"><div class="kpi-n">Latest Month</div><div class="kpi-v">{latest_total:,.0f}</div><div class="kpi-c fl">{latest_month} · {data_mode}</div></div>
      <div class="kpi"><div class="kpi-n">Top Competitor</div><div class="kpi-v">{html.escape(str(top_name))}</div><div class="kpi-c fl">{top_weight:,.0f} kg</div></div>
      <div class="kpi"><div class="kpi-n">Top Importer</div><div class="kpi-v" style="font-size:16px">{html.escape(str(dest_top))}</div><div class="kpi-c fl">{total_shipments:,.0f} B/L count</div></div>
    </div>
    """, unsafe_allow_html=True)

    card_html = ""
    for _, row in top_summary.head(4).iterrows():
        name = row["competitor"]
        weight = row["weight_kg"]
        share = (weight / total_weight * 100) if total_weight else 0
        latest_weight = view[(view["competitor"] == name) & (view["month"] == latest_month)]["weight_kg"].sum()
        card_html += (
            f'<div class="competitor-card">{company_badge(name)}'
            f'<div class="co-k">B/L Weight Leader</div>'
            f'<div class="co-name">{html.escape(str(name))}</div>'
            f'<div class="co-val">{weight:,.0f}</div>'
            f'<div class="co-sub">Share {share:.1f}% · Latest {latest_weight:,.0f} kg</div>'
            f'</div>'
        )
    st.markdown(f'<div class="competitor-grid">{card_html}</div>', unsafe_allow_html=True)

    trend_col, share_col = st.columns([1.45, 1], gap="medium")
    with trend_col:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Monthly Export Weight Trend</span><span class="p-m">Competitor by month</span></div><div class="p-body">', unsafe_allow_html=True)
        fig_trend = go.Figure()
        for name in top_summary.head(8)["competitor"].tolist():
            sub = view[view["competitor"] == name].sort_values("month")
            fig_trend.add_trace(go.Scatter(
                x=sub["month"],
                y=sub["weight_kg"],
                name=name,
                mode="lines+markers",
                line=dict(width=2.4),
                hovertemplate="%{x}<br>%{fullData.name}: %{y:,.0f} kg<extra></extra>",
            ))
        chart_layout(fig_trend, 330)
        fig_trend.update_layout(xaxis_title=None, yaxis_title="Weight kg")
        st.plotly_chart(fig_trend, use_container_width=True, config=CHART_CONFIG)
        st.markdown('</div></div>', unsafe_allow_html=True)

    with share_col:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Competitor Share</span><span class="p-m">Selected period</span></div><div class="p-body">', unsafe_allow_html=True)
        share_df = top_summary.head(10).sort_values("weight_kg")
        fig_share = go.Figure(go.Bar(
            x=share_df["weight_kg"],
            y=share_df["competitor"],
            orientation="h",
            marker_color=GOLD,
            hovertemplate="%{y}<br>Weight: %{x:,.0f} kg<extra></extra>",
        ))
        chart_layout(fig_share, 330)
        fig_share.update_layout(xaxis_title="Weight kg", yaxis_title=None, showlegend=False)
        st.plotly_chart(fig_share, use_container_width=True, config=CHART_CONFIG)
        st.markdown('</div></div>', unsafe_allow_html=True)

    heat_col, dest_col = st.columns([1.2, 1], gap="medium")
    with heat_col:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Monthly Heatmap</span><span class="p-m">Weight concentration</span></div><div class="p-body">', unsafe_allow_html=True)
        heat = view.pivot_table(index="competitor", columns="month", values="weight_kg", aggfunc="sum", fill_value=0)
        heat = heat.reindex(top_summary["competitor"].tolist()).head(12)
        fig_heat = go.Figure(go.Heatmap(
            z=heat.values,
            x=heat.columns,
            y=heat.index,
            colorscale=[[0, "#11161F"], [0.5, "#2D7FF9"], [1, "#E8B339"]],
            hovertemplate="%{y}<br>%{x}: %{z:,.0f} kg<extra></extra>",
            colorbar=dict(title="kg"),
        ))
        chart_layout(fig_heat, 360)
        fig_heat.update_layout(xaxis_title=None, yaxis_title=None)
        st.plotly_chart(fig_heat, use_container_width=True, config=CHART_CONFIG)
        st.markdown('</div></div>', unsafe_allow_html=True)

    with dest_col:
        st.markdown(f'<div class="panel"><div class="p-head"><span class="p-t">Importer / Destination Detail</span><span class="p-m">{data_mode}</span></div><div class="p-body">', unsafe_allow_html=True)
        st.markdown(
            "".join([
                f'<span class="co-pill">{company_badge(c)}{html.escape(str(c))}</span>'
                for c in top_summary.head(6)["competitor"].tolist()
            ]),
            unsafe_allow_html=True,
        )
        dest_table = dest_view.sort_values("weight_kg", ascending=False).head(14).copy()
        st.markdown(dataframe_to_dark_table(dest_table), unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

    if not product_view.empty:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Product Description Signal</span><span class="p-m">Raw product text aggregation</span></div><div class="p-body">', unsafe_allow_html=True)
        product_table = product_view.sort_values("weight_kg", ascending=False).head(20).copy()
        st.markdown(dataframe_to_dark_table(product_table), unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Competitor Export Summary Table</span><span class="p-m">Pivot-style table</span></div><div class="p-body">', unsafe_allow_html=True)
    summary_table = view.pivot_table(index="competitor", columns="month", values="weight_kg", aggfunc="sum", fill_value=0)
    summary_table["합계"] = summary_table.sum(axis=1)
    summary_table = summary_table.sort_values("합계", ascending=False).reset_index()
    st.markdown(dataframe_to_dark_table(summary_table), unsafe_allow_html=True)
    excel_download_button(
        "📊 경쟁사 수출동향 엑셀 다운로드",
        {
            "Monthly Weight": view,
            "Summary Pivot": summary_table,
            "Importer Detail": dest_view,
            "Product Description": product_view,
        },
        f"kcc_lvt_competitor_export_{datetime.now().strftime('%Y%m%d')}.xlsx",
        "competitor_export_excel_download",
    )
    st.caption("표현 기준: ImportYeti / 미국 항만 수입 B/L 데이터의 Weight 기준 추정치. 업체명 정규화, 누락 데이터, 중복 수입자명은 원본 엑셀 반영 단계에서 보정 예정입니다.")
    st.markdown('</div></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 🎨 DESIGN INTELLIGENCE
# ════════════════════════════════════════════════════════════
elif menu == "🎨 Design Intelligence":
    st.markdown('<div class="sec"><span class="sec-t">Design Intelligence</span><span class="sec-s">미국 바닥재 디자인 트렌드 · 제품 레퍼런스</span><span class="live"><span class="dot"></span>FCW + FCNews</span></div>', unsafe_allow_html=True)

    design_source_mode = st.radio(
        "Design Source",
        ["FCW + FCNews", "FCW only", "FCNews only"],
        horizontal=True,
        label_visibility="collapsed",
        key="design_source_mode",
    )
    design_items = collect_design_articles(limit=24, source_mode=design_source_mode)
    keyword_df = extract_design_keywords(design_items)
    taxonomy_df = build_design_taxonomy(design_items)
    implication_df = build_product_implications(keyword_df)
    source_keyword_df = build_source_keyword_comparison(design_items)
    guide_df = collect_fcnews_guides()

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Design Articles", f"{len(design_items):,.0f}")
    with k2:
        st.metric("Top Keyword", keyword_df.iloc[0]["Keyword"] if len(keyword_df) else "N/A")
    with k3:
        material_top = taxonomy_df[taxonomy_df["Axis"] == "Material"].sort_values("Signal", ascending=False).iloc[0]
        st.metric("Material Signal", material_top["Trend Bucket"])
    with k4:
        pattern_top = taxonomy_df[taxonomy_df["Axis"] == "Pattern"].sort_values("Signal", ascending=False).iloc[0]
        st.metric("Pattern Signal", pattern_top["Trend Bucket"])

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Trend Keyword Radar</span><span class="p-m">FCW + FCNews scan</span></div><div class="p-body">', unsafe_allow_html=True)
    st.markdown(render_trend_pills(keyword_df), unsafe_allow_html=True)
    kw_col, tax_col = st.columns([1, 1], gap="medium")
    with kw_col:
        fig_kw = go.Figure(go.Bar(
            x=keyword_df.head(10).sort_values("Mentions")["Mentions"],
            y=keyword_df.head(10).sort_values("Mentions")["Keyword"],
            orientation="h",
            marker_color=GOLD,
            hovertemplate="%{y}<br>Mentions: %{x}<extra></extra>",
        ))
        chart_layout(fig_kw, 280)
        fig_kw.update_layout(xaxis_title="Mentions", yaxis_title=None, showlegend=False)
        st.plotly_chart(fig_kw, use_container_width=True, config=CHART_CONFIG)
    with tax_col:
        if len(source_keyword_df):
            fig_src = go.Figure()
            for source, color in [("FCW", T["accent"]), ("FCNews", GOLD)]:
                sub = source_keyword_df[source_keyword_df["Source"] == source].head(6)
                fig_src.add_trace(go.Bar(
                    x=sub["Mentions"],
                    y=sub["Keyword"],
                    name=source,
                    orientation="h",
                    marker_color=color,
                    hovertemplate=f"{source}<br>%{{y}}: %{{x}}<extra></extra>",
                ))
            chart_layout(fig_src, 280)
            fig_src.update_layout(barmode="group", xaxis_title="Mentions", yaxis_title=None)
            st.plotly_chart(fig_src, use_container_width=True, config=CHART_CONFIG)
        else:
            tax_pivot = taxonomy_df.sort_values(["Axis", "Signal"], ascending=[True, False]).groupby("Axis").head(4)
            fig_tax = go.Figure(go.Bar(
                x=tax_pivot["Signal"],
                y=tax_pivot["Axis"] + " · " + tax_pivot["Trend Bucket"],
                orientation="h",
                marker_color=T["accent"],
                hovertemplate="%{y}<br>Signal: %{x}<extra></extra>",
            ))
            chart_layout(fig_tax, 280)
            fig_tax.update_layout(xaxis_title="Signal", yaxis_title=None, showlegend=False)
            st.plotly_chart(fig_tax, use_container_width=True, config=CHART_CONFIG)
    st.markdown('</div></div>', unsafe_allow_html=True)

    article_col, insight_col = st.columns([1.45, 1], gap="medium")
    with article_col:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Design Trend Articles</span><span class="p-m">Visual reference cards</span></div><div class="p-body">', unsafe_allow_html=True)
        if design_items:
            def design_card(item, featured=False):
                title = html.escape(item.get("title", ""))
                link = html.escape(item.get("link", ""))
                published = html.escape(item.get("published", "") or "Latest")
                summary = html.escape(item.get("summary", ""))
                image = html.escape(item.get("image", "") or "")
                tag = html.escape(f'{item.get("source_group", "Source")} · {item.get("design_source_category", "Design")}')
                media = f'<img src="{image}" alt="{title}" loading="lazy"/>' if image else f'<div class="fcw-fallback"><span>{tag}</span></div>'
                summary_html = f'<div class="fcw-summary">{summary}</div>' if summary else ""
                klass = "fcw-card featured" if featured else "fcw-card"
                return (
                    f'<div class="{klass}">'
                    f'<div class="fcw-media">{media}</div>'
                    f'<div class="fcw-body">'
                    f'<div class="fcw-meta">{published} · {tag}</div>'
                    f'<a class="fcw-title" href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>'
                    f'{summary_html}'
                    f'<a class="fcw-read" href="{link}" target="_blank" rel="noopener noreferrer">Read More &rarr;</a>'
                    f'</div></div>'
                )
            st.markdown(design_card(design_items[0], featured=True), unsafe_allow_html=True)
            st.markdown(f'<div class="fcw-grid">{"".join(design_card(item) for item in design_items[1:7])}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="placeholder"><span style="font-size:26px">DESIGN</span><span>디자인 기사 데이터를 불러올 수 없습니다</span></div>', unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

    with insight_col:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Material / Color / Pattern</span><span class="p-m">Design buckets</span></div><div class="p-body">', unsafe_allow_html=True)
        st.markdown(dataframe_to_dark_table(taxonomy_df.sort_values(["Axis", "Signal"], ascending=[True, False]).groupby("Axis").head(5)), unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">FCNews Guide Watch</span><span class="p-m">Supplements / category links</span></div><div class="p-body">', unsafe_allow_html=True)
        guide_links = guide_df.copy()
        guide_links["링크"] = guide_links["링크"].map(lambda x: f'<a href="{html.escape(x)}" target="_blank" rel="noopener noreferrer">Open</a>')
        st.markdown(dataframe_to_dark_table(guide_links), unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

        st.markdown(
            f"""
            <div class="esg-card">
              <div class="esg-k">ESG Design Reference</div>
              <div class="esg-t">친환경/지속가능성 메시지 참고</div>
              <div class="esg-d">
                해외 고객 대응이나 디자인 콘셉트 검토 시, 회사 공식 ESG 리포트의 환경·공급망·고객만족 메시지를 함께 참고할 수 있습니다.
              </div>
              <div class="esg-tags">
                <span class="esg-tag">친환경 소재 스토리</span>
                <span class="esg-tag">공급망 신뢰</span>
                <span class="esg-tag">고객 제안 문구</span>
              </div>
              <div class="esg-actions">
                <a class="esg-btn" href="{KCC_ESG_LATEST_EN_URL}" target="_blank" rel="noopener noreferrer">English ESG Report</a>
                <a class="esg-btn secondary" href="{KCC_ESG_REPORT_PAGE_EN}" target="_blank" rel="noopener noreferrer">Official ESG Page</a>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Product Implication</span><span class="p-m">KCC LVT lens</span></div><div class="p-body">', unsafe_allow_html=True)
        st.markdown(dataframe_to_dark_table(implication_df), unsafe_allow_html=True)
        st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Design Moodboard</span><span class="p-m">Visual references</span></div><div class="p-body">', unsafe_allow_html=True)
    st.markdown(render_moodboard(design_items), unsafe_allow_html=True)
    st.caption("이미지는 FCW 기사에서 확인 가능한 대표 이미지를 우선 사용하며, 이미지가 없는 경우 대체 디자인 레퍼런스 카드로 표시됩니다.")
    st.markdown('</div></div>', unsafe_allow_html=True)

    export_design = pd.DataFrame(design_items)
    excel_download_button(
        "📊 Design Intelligence 엑셀 다운로드",
        {
            "Design Articles": export_design,
            "Keyword Radar": keyword_df,
            "Source Keyword Compare": source_keyword_df,
            "Material Color Pattern": taxonomy_df,
            "Product Implication": implication_df,
            "FCNews Guide Watch": guide_df,
        },
        f"kcc_lvt_design_intelligence_{datetime.now().strftime('%Y%m%d')}.xlsx",
        "design_intelligence_excel_download",
    )

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

    def fcw_card(item, featured=False):
        title = html.escape(item.get("title", ""))
        link = html.escape(item.get("link", ""))
        published = html.escape(item.get("published", "") or "Latest")
        summary = html.escape(item.get("summary", ""))
        image = html.escape(item.get("image", "") or "")
        tag = html.escape(item.get("category", fcw_category))
        media = (
            f'<img src="{image}" alt="{title}" loading="lazy"/>'
            if image else
            f'<div class="fcw-fallback"><span>{tag}</span></div>'
        )
        summary_html = f'<div class="fcw-summary">{summary}</div>' if summary else ""
        klass = "fcw-card featured" if featured else "fcw-card"
        return (
            f'<div class="{klass}">'
            f'<div class="fcw-media">{media}</div>'
            f'<div class="fcw-body">'
            f'<div class="fcw-meta">{published} · Floor Covering Weekly</div>'
            f'<a class="fcw-title" href="{link}" target="_blank" rel="noopener noreferrer">{title}</a>'
            f'{summary_html}'
            f'<a class="fcw-read" href="{link}" target="_blank" rel="noopener noreferrer">Read More &rarr;</a>'
            f'</div>'
            f'</div>'
        )

    left, right = st.columns([2, 1], gap="medium")
    with left:
        st.markdown(f'<div class="panel"><div class="p-head"><span class="p-t">Featured Articles</span><span class="p-m">{fcw_category}</span></div><div class="p-body">', unsafe_allow_html=True)
        if fcw_items:
            st.markdown(fcw_card(fcw_items[0], featured=True), unsafe_allow_html=True)
            cards = "".join(fcw_card(item) for item in fcw_items[1:9])
            st.markdown(f'<div class="fcw-grid">{cards}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="placeholder"><span style="font-size:26px">📰</span><span>FCW 기사를 불러올 수 없습니다</span></div>', unsafe_allow_html=True)
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

        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Reading Queue</span><span class="p-m">Quick scan</span></div><div class="p-body">', unsafe_allow_html=True)
        for item in fcw_items[:6]:
            title = html.escape(item.get("title", ""))
            link = html.escape(item.get("link", ""))
            published = html.escape(item.get("published", "") or "Latest")
            st.markdown(
                f'<div class="news"><a href="{link}" target="_blank" rel="noopener noreferrer" style="font-size:13px;font-weight:800">{title}</a><div class="news-t">{published}</div></div>',
                unsafe_allow_html=True,
            )
        st.markdown('</div></div>', unsafe_allow_html=True)

    fcw_export = pd.DataFrame(fcw_items)
    excel_download_button(
        "📊 FCW 기사 목록 엑셀 다운로드",
        {"FCW Articles": fcw_export},
        f"kcc_lvt_fcw_articles_{datetime.now().strftime('%Y%m%d')}.xlsx",
        "fcw_excel_download",
    )

# ════════════════════════════════════════════════════════════
# 🏡 HOUSING
# ════════════════════════════════════════════════════════════
elif menu == "🏡 Housing":
    st.markdown('<div class="sec"><span class="sec-t">US Housing Market</span><span class="sec-s">허가 · 착공 · 완공 · 판매 · 재고</span></div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="kpi-strip" style="grid-template-columns:repeat(5,1fr);">
      <div class="kpi"><div class="kpi-n">Permits</div><div class="kpi-v">{v_permits:,.0f}<span style="font-size:12px;color:{T['text3']}">K</span></div>{kpi_change(d_permits)}</div>
      <div class="kpi"><div class="kpi-n">Starts</div><div class="kpi-v">{v_housing:,.0f}<span style="font-size:12px;color:{T['text3']}">K</span></div>{kpi_change(d_housing)}</div>
      <div class="kpi"><div class="kpi-n">Completions</div><div class="kpi-v">{v_complete:,.0f}<span style="font-size:12px;color:{T['text3']}">K</span></div>{kpi_change(d_complete)}</div>
      <div class="kpi"><div class="kpi-n">Existing Sales</div><div class="kpi-v">{v_existing:,.2f}</div>{kpi_change(d_existing)}</div>
      <div class="kpi"><div class="kpi-n">Monthly Supply</div><div class="kpi-v">{v_supply:.1f}</div>{kpi_change(d_supply)}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Housing Pipeline</span><span class="p-m">Permits → Starts → Completions</span></div><div class="p-guide"><b>활용 포인트</b> 건축허가는 선행 수요, 착공은 현재 프로젝트 흐름, 완공은 바닥재 투입 타이밍에 가까운 지표로 함께 봅니다.</div><div class="p-body">', unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_permits["date"], y=df_permits["건축허가"], name="Building Permits (K)",
        line=dict(color="#7AA7FF", width=2),
        hovertemplate="%{x|%Y-%m-%d}<br>Permits: %{y:,.0f}K<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df_housing["date"], y=df_housing["주택착공"], name="Housing Starts (K)",
        line=dict(color=T['accent'], width=2),
        hovertemplate="%{x|%Y-%m-%d}<br>Housing Starts: %{y:,.0f}K<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df_complete["date"], y=df_complete["주택완공"], name="Completions (K)",
        line=dict(color=GOLD, width=2),
        hovertemplate="%{x|%Y-%m-%d}<br>Completions: %{y:,.0f}K<extra></extra>",
    ))
    chart_layout(fig, 320)
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
    st.markdown('</div></div>', unsafe_allow_html=True)

    c_sales, c_supply = st.columns([1.2, 1], gap="medium")
    with c_sales:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Home Sales Signal</span><span class="p-m">New vs Existing</span></div><div class="p-guide"><b>활용 포인트</b> 신규주택은 builder 수요, 기존주택 판매는 리모델링·교체 수요 분위기와 연결해서 봅니다.</div><div class="p-body">', unsafe_allow_html=True)
        fig_sales_home = go.Figure()
        fig_sales_home.add_trace(go.Scatter(
            x=df_newsales["date"], y=df_newsales["신규주택판매"], name="New Home Sales (K)",
            line=dict(color=GOLD, width=2),
            hovertemplate="%{x|%Y-%m-%d}<br>New Home Sales: %{y:,.0f}K<extra></extra>",
        ))
        fig_sales_home.add_trace(go.Scatter(
            x=df_existing_sales["date"], y=df_existing_sales["기존주택판매"], name="Existing Home Sales", yaxis="y2",
            line=dict(color=T["up"], width=2, dash="dot"),
            hovertemplate="%{x|%Y-%m-%d}<br>Existing Sales: %{y:,.2f}<extra></extra>",
        ))
        fig_sales_home.update_layout(yaxis2=dict(overlaying="y", side="right", gridcolor='rgba(0,0,0,0)'))
        chart_layout(fig_sales_home, 280)
        st.plotly_chart(fig_sales_home, use_container_width=True, config=CHART_CONFIG)
        st.markdown('</div></div>', unsafe_allow_html=True)
    with c_supply:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">New Home Inventory Pressure</span><span class="p-m">Monthly supply</span></div><div class="p-guide"><b>활용 포인트</b> 재고 개월 수가 높아지면 builder 가격 압박과 신규 주문 보수화 가능성을 같이 체크합니다.</div><div class="p-body">', unsafe_allow_html=True)
        fig_supply = go.Figure(go.Scatter(
            x=df_month_supply["date"], y=df_month_supply["신규주택재고개월"], name="Monthly Supply",
            line=dict(color=T["down"], width=2.5),
            fill="tozeroy",
            fillcolor="rgba(240,69,74,0.08)",
            hovertemplate="%{x|%Y-%m-%d}<br>Monthly Supply: %{y:.1f} months<extra></extra>",
        ))
        chart_layout(fig_supply, 280)
        fig_supply.update_layout(showlegend=False)
        st.plotly_chart(fig_supply, use_container_width=True, config=CHART_CONFIG)
        st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Housing Indicator Table</span><span class="p-m">MoM / YoY comparison</span></div><div class="p-guide"><b>활용 포인트</b> 그래프에서 방향성을 보고, 표에서 전월·전년 대비 변화율로 보고용 문장을 정리합니다.</div><div class="p-body">', unsafe_allow_html=True)
    housing_rows = [
        indicator_compare_row("Building Permits", df_permits, "건축허가", "K", 0),
        indicator_compare_row("Housing Starts", df_housing, "주택착공", "K", 0),
        indicator_compare_row("Housing Completions", df_complete, "주택완공", "K", 0),
        indicator_compare_row("New Home Sales", df_newsales, "신규주택판매", "K", 0),
        indicator_compare_row("Existing Home Sales", df_existing_sales, "기존주택판매", "-", 2),
        indicator_compare_row("Monthly Supply", df_month_supply, "신규주택재고개월", "months", 1),
        indicator_compare_row("30Y Mortgage", df_mortgage, "모기지금리", "%", 2),
    ]
    st.markdown(
        f"""
        <table class="dt">
          <thead>
            <tr>
              <th>지표</th><th>단위</th><th>기준일</th><th>현재</th>
              <th>전월</th><th>전월대비</th><th>전년</th><th>전년대비</th>
            </tr>
          </thead>
          <tbody>{build_market_compare_rows(housing_rows)}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )
    st.caption("전월/전년 값은 해당 기준일 이전의 가장 가까운 발표값 기준입니다.")
    excel_download_button(
        "📊 Housing 데이터 엑셀 다운로드",
        {
            "Housing Starts": df_housing,
            "Building Permits": df_permits,
            "Housing Completions": df_complete,
            "New Home Sales": df_newsales,
            "Existing Home Sales": df_existing_sales,
            "Monthly Supply": df_month_supply,
            "Mortgage": df_mortgage,
        },
        f"kcc_lvt_housing_{datetime.now().strftime('%Y%m%d')}.xlsx",
        "housing_excel_download",
    )
    st.markdown('</div></div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# 📈 MACRO
# ════════════════════════════════════════════════════════════
elif menu == "📈 Macro":
    st.markdown('<div class="sec"><span class="sec-t">Macro Indicators</span><span class="sec-s">CPI · 금리 · 건자재 유통 · 자재 가격</span></div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div class="kpi-strip" style="grid-template-columns:repeat(4,1fr);">
      <div class="kpi"><div class="kpi-n">CPI</div><div class="kpi-v">{v_cpi:.1f}</div>{kpi_change(d_cpi)}</div>
      <div class="kpi"><div class="kpi-n">Fed Funds</div><div class="kpi-v">{v_fedfunds:.2f}<span style="font-size:12px;color:{T['text3']}">%</span></div><div class="kpi-c fl">policy</div></div>
      <div class="kpi"><div class="kpi-n">Building Retail Sales</div><div class="kpi-v">{v_building_retail:,.0f}</div>{kpi_change(d_building_retail)}</div>
      <div class="kpi"><div class="kpi-n">Lumber PPI</div><div class="kpi-v">{v_lumber_ppi:.1f}</div>{kpi_change(d_lumber_ppi)}</div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">CPI & Fed Funds Rate</span><span class="p-m">2019–Present</span></div><div class="p-guide"><b>활용 포인트</b> CPI와 정책금리는 모기지 금리, 소비 심리, 환율 흐름에 영향을 주는 큰 배경 지표로 봅니다.</div><div class="p-body">', unsafe_allow_html=True)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_cpi["date"], y=df_cpi["CPI"], name="CPI",
        line=dict(color=GOLD, width=2),
        hovertemplate="%{x|%Y-%m-%d}<br>CPI: %{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=df_fedfunds["date"], y=df_fedfunds["기준금리"], name="Fed Funds (%)", yaxis="y2",
        line=dict(color=T['accent'], width=2, dash="dot"),
        hovertemplate="%{x|%Y-%m-%d}<br>Fed Funds: %{y:.2f}%<extra></extra>",
    ))
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", gridcolor='rgba(0,0,0,0)'))
    chart_layout(fig, 320)
    st.plotly_chart(fig, use_container_width=True, config=CHART_CONFIG)
    macro_rows = [
        indicator_compare_row("CPI", df_cpi, "CPI", "-", 2),
        indicator_compare_row("Fed Funds", df_fedfunds, "기준금리", "%", 2),
    ]
    st.markdown(
        f"""
        <table class="dt">
          <thead>
            <tr>
              <th>지표</th><th>단위</th><th>기준일</th><th>현재</th>
              <th>전월</th><th>전월대비</th><th>전년</th><th>전년대비</th>
            </tr>
          </thead>
          <tbody>{build_market_compare_rows(macro_rows)}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )
    st.caption("전월/전년 값은 해당 기준일 이전의 가장 가까운 발표값 기준입니다.")
    st.markdown('</div></div>', unsafe_allow_html=True)

    macro_c1, macro_c2 = st.columns([1.15, 1], gap="medium")
    with macro_c1:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Building Materials Retail Sales</span><span class="p-m">Demand proxy</span></div><div class="p-guide"><b>활용 포인트</b> 홈센터·건자재 유통 채널 매출 흐름으로 리모델링 및 자재 구매 분위기를 보조 확인합니다.</div><div class="p-body">', unsafe_allow_html=True)
        fig_retail = go.Figure(go.Scatter(
            x=df_building_retail["date"],
            y=df_building_retail["건자재유통매출"],
            name="Building Materials Retail Sales",
            line=dict(color=T["up"], width=2.4),
            fill="tozeroy",
            fillcolor="rgba(21,184,107,0.08)",
            hovertemplate="%{x|%Y-%m-%d}<br>Retail Sales: %{y:,.1f}<extra></extra>",
        ))
        chart_layout(fig_retail, 280)
        fig_retail.update_layout(showlegend=False)
        st.plotly_chart(fig_retail, use_container_width=True, config=CHART_CONFIG)
        st.caption("건자재/자재 유통 채널의 매출 흐름으로 홈센터·리모델링 수요 분위기를 보조적으로 확인합니다.")
        st.markdown('</div></div>', unsafe_allow_html=True)
    with macro_c2:
        st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Material Price Pressure</span><span class="p-m">PPI signals</span></div><div class="p-guide"><b>활용 포인트</b> 직접 원료 지표는 아니지만 미국 건축 자재 가격 압력을 읽는 보조 신호로 활용합니다.</div><div class="p-body">', unsafe_allow_html=True)
        fig_ppi = go.Figure()
        fig_ppi.add_trace(go.Scatter(
            x=df_lumber_ppi["date"], y=df_lumber_ppi["Lumber PPI"], name="Lumber PPI",
            line=dict(color=GOLD, width=2),
            hovertemplate="%{x|%Y-%m-%d}<br>Lumber PPI: %{y:,.1f}<extra></extra>",
        ))
        fig_ppi.add_trace(go.Scatter(
            x=df_building_ppi["date"], y=df_building_ppi["건자재유통PPI"], name="Building Material PPI",
            line=dict(color=T["accent"], width=2, dash="dot"),
            hovertemplate="%{x|%Y-%m-%d}<br>Building Material PPI: %{y:,.1f}<extra></extra>",
        ))
        chart_layout(fig_ppi, 280)
        st.plotly_chart(fig_ppi, use_container_width=True, config=CHART_CONFIG)
        st.caption("LVT 직접 원료는 아니지만, 미국 건축/자재 가격 압박을 읽는 보조 지표로 활용합니다.")
        st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">Macro Extended Table</span><span class="p-m">MoM / YoY comparison</span></div><div class="p-guide"><b>활용 포인트</b> 거시 지표는 단일 수치보다 전월·전년 대비 방향성을 함께 보고 시장 코멘트의 근거로 씁니다.</div><div class="p-body">', unsafe_allow_html=True)
    extended_macro_rows = [
        indicator_compare_row("CPI", df_cpi, "CPI", "-", 2),
        indicator_compare_row("Fed Funds", df_fedfunds, "기준금리", "%", 2),
        indicator_compare_row("Building Materials Retail Sales", df_building_retail, "건자재유통매출", "-", 1),
        indicator_compare_row("Lumber PPI", df_lumber_ppi, "Lumber PPI", "-", 1),
        indicator_compare_row("Building Material PPI", df_building_ppi, "건자재유통PPI", "-", 1),
    ]
    st.markdown(
        f"""
        <table class="dt">
          <thead>
            <tr>
              <th>지표</th><th>단위</th><th>기준일</th><th>현재</th>
              <th>전월</th><th>전월대비</th><th>전년</th><th>전년대비</th>
            </tr>
          </thead>
          <tbody>{build_market_compare_rows(extended_macro_rows)}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )
    excel_download_button(
        "📊 Macro 데이터 엑셀 다운로드",
        {
            "CPI": df_cpi,
            "Fed Funds": df_fedfunds,
            "Building Retail Sales": df_building_retail,
            "Lumber PPI": df_lumber_ppi,
            "Building Material PPI": df_building_ppi,
        },
        f"kcc_lvt_macro_{datetime.now().strftime('%Y%m%d')}.xlsx",
        "macro_excel_download",
    )
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
    tariff_timeline = pd.DataFrame([
        {"시점": "2026.02", "구분": "상호관세 판결", "핵심 내용": "미 연방대법원, IEEPA 근거 상호관세 위법 판결로 상호관세 무력화"},
        {"시점": "2026.03", "구분": "301조 조사 착수", "핵심 내용": "USTR, 과잉생산·강제노동 명분으로 무역법 301조 조사 착수"},
        {"시점": "현재 적용", "구분": "122조 글로벌 관세", "핵심 내용": "무역법 122조 기반 10% 글로벌 관세 부과 중. 2026.07.24 만료 예정"},
        {"시점": "2026.06.02", "구분": "추가 관세안", "핵심 내용": "강제노동 분야 60개국 대상 10%/12.5% 추가 관세안 발표. 한국은 12.5% 그룹 포함"},
        {"시점": "2026.07.07", "구분": "의견 수렴", "핵심 내용": "공청회 등 의견수렴 후 최종 확정 예정. 대체 관세 도입 가능성 모니터링 필요"},
    ])
    tariff_scenario = pd.DataFrame([
        {"원산지": "한국산", "기존 구조": "한미 FTA 0%", "현재/예상 부담": "글로벌 10%에서 2.5%p 추가 시 총 12.5%", "영업 메시지": "기존 FTA 0% 논리는 약화되나 중국산 대비 우위는 유지"},
        {"원산지": "중국산", "기존 구조": "기본 5.3% + Section 301 25%", "현재/예상 부담": "글로벌 10% 포함 약 40.3% 수준", "영업 메시지": "한국산과의 관세 격차 약 28~30%p 유지"},
    ])
    tariff_actions = pd.DataFrame([
        {"영역": "단기", "대응 방향": "2026.07.24 이전 선적 가능 물량 선제 출고 협의 및 계약 타이밍 점검"},
        {"영역": "가격", "대응 방향": "12.5% 확정 대비 관세 분담 시나리오를 사전 수립하고 가격 통보에 반영"},
        {"영역": "영업", "대응 방향": "한국산도 일부 관세 부담이 생기지만 중국산 대비 30%p 내외 우위 메시지 재정비"},
        {"영역": "모니터링", "대응 방향": "2026.07.07 청문회, 최종 확정안, 총 15% 협상 결과를 지속 추적"},
    ])
    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">미국 추가 관세 대응 브리핑</span><span class="p-m">USTR · Scenario</span></div><div class="p-body">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="summary-grid">
          <div class="summary-card"><div class="summary-k">현 상황</div><div class="summary-v">122조 기반 10% 글로벌 관세가 적용 중이며, 2026.07.24 만료 전후 관세 공백과 정책 불확실성 확인이 필요합니다.</div></div>
          <div class="summary-card"><div class="summary-k">한국산 리스크</div><div class="summary-v">한국산은 기존 글로벌 10%에서 2.5%p가 추가되어 총 12.5%가 될 가능성이 있어, FTA 0% 영업논리는 일부 약화될 수 있습니다.</div></div>
          <div class="summary-card"><div class="summary-k">셀링포인트</div><div class="summary-v">중국산 대비 관세 격차는 약 28~30%p 유지될 가능성이 높아, 전환 영업 메시지는 여전히 유효합니다.</div></div>
        </div>
        <div class="report-note">첨부 보고자료의 핵심을 대시보드용으로 요약했습니다. 실제 적용 전에는 확정 고시와 관세사 검토가 필요합니다.</div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(dataframe_to_dark_table(tariff_timeline), unsafe_allow_html=True)
    c_scenario, c_action = st.columns([1.1, 1], gap="medium")
    with c_scenario:
        st.markdown(f'<div style="font-size:12px;font-weight:700;color:{T["text"]};margin:8px 0">관세 구조 시나리오</div>', unsafe_allow_html=True)
        st.markdown(dataframe_to_dark_table(tariff_scenario), unsafe_allow_html=True)
    with c_action:
        st.markdown(f'<div style="font-size:12px;font-weight:700;color:{T["text"]};margin:8px 0">당사 대응 방안</div>', unsafe_allow_html=True)
        st.markdown(dataframe_to_dark_table(tariff_actions), unsafe_allow_html=True)
    st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="panel"><div class="p-head"><span class="p-t">📋 LVT 관세 참고 (미국 수입)</span><span class="p-m">실무 참고용</span></div><div class="p-body">', unsafe_allow_html=True)
    tref = pd.DataFrame([
        {"구분": "HTS 코드", "내용": "3918.10 (비닐 바닥재)", "비고": "품목분류 변동 가능"},
        {"구분": "한미 FTA", "내용": "기본 관세 0%", "비고": "원산지증명(CO) 필요"},
        {"구분": "임시 관세", "내용": f"{st.session_state.sim_duty:.0f}% (현재)", "비고": "정책 변동 모니터링"},
        {"구분": "MPF", "내용": "0.3464% (Min $33.58/Max $651.50)", "비고": "CO 보완 시 면제 가능"},
        {"구분": "HMF", "내용": "0.125%", "비고": "해상운송 부과"},
    ])
    st.markdown(dataframe_to_dark_table(tref), unsafe_allow_html=True)
    st.caption("⚠️ 참고용 · 실제 통관 시 관세사·세관 확인 필요")
    excel_download_button(
        "📊 FX/Tariff 데이터 엑셀 다운로드",
        {
            "FX": df_fx,
            "Tariff Reference": tref,
            "Tariff Timeline": tariff_timeline,
            "Tariff Scenario": tariff_scenario,
            "Tariff Actions": tariff_actions,
        },
        f"kcc_lvt_fx_tariff_{datetime.now().strftime('%Y%m%d')}.xlsx",
        "fx_tariff_excel_download",
    )
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
