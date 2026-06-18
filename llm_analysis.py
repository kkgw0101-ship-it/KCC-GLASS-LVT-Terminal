"""
llm_analysis.py
LVT Intelligence Dashboard — LLM 분석 모듈
- 무역/물류 뉴스를 RSS로 수집
- Claude API로 분석 (뉴스 요약 + 시장 브리핑)
"""

import feedparser
import anthropic
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import streamlit as st
from urllib.parse import urljoin
import re

# ── 뉴스 RSS 피드 (모두 무료, Google News 기반) ─────────────────
NEWS_FEEDS = {
    "freight": "https://news.google.com/rss/search?q=container+freight+shipping+rate+SCFI&hl=en-US&gl=US&ceid=US:en",
    "tariff":  "https://news.google.com/rss/search?q=US+tariff+import+flooring+vinyl&hl=en-US&gl=US&ceid=US:en",
    "housing": "https://news.google.com/rss/search?q=US+housing+market+mortgage+construction&hl=en-US&gl=US&ceid=US:en",
}

FCW_URLS = {
    "All Latest": "https://www.floorcoveringweekly.com/",
    "Features": "https://www.floorcoveringweekly.com/main/features",
    "Products": "https://www.floorcoveringweekly.com/main/products2",
    "Retail": "https://www.floorcoveringweekly.com/main/retail",
    "Business Builder": "https://www.floorcoveringweekly.com/main/business-builder",
    "Sustainability": "https://www.floorcoveringweekly.com/main/sustainability",
    "Technology": "https://www.floorcoveringweekly.com/main/technology",
    "Style & Design": "https://www.floorcoveringweekly.com/main/style-design",
}


@st.cache_data(ttl=1800)  # 30분 캐시
def fetch_news(category="freight", limit=8):
    """RSS 피드에서 뉴스 헤드라인 수집"""
    url = NEWS_FEEDS.get(category, NEWS_FEEDS["freight"])
    feed = feedparser.parse(url)
    items = []
    for e in feed.entries[:limit]:
        items.append({
            "title": e.get("title", ""),
            "link": e.get("link", ""),
            "published": e.get("published", ""),
            "source": e.get("source", {}).get("title", "") if hasattr(e, "source") else "",
        })
    return items


@st.cache_data(ttl=1800)
def fetch_fcw_news(category="All Latest", limit=12):
    """Floor Covering Weekly 최신 기사 목록을 가져옵니다."""
    url = FCW_URLS.get(category, FCW_URLS["All Latest"])
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        return [{"title": "FCW 기사를 불러오지 못했습니다.", "link": url, "published": "", "summary": str(e), "source": "FCW"}]

    date_re = re.compile(
        r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), "
        r"[A-Za-z]+ \d{1,2}, \d{4}"
    )
    skip_titles = {
        "Features", "News", "Products", "Business Builder", "Retail", "Sustainability",
        "Technology", "Style & Design", "Research + Data", "Awards Programs", "Advertising",
        "Archive", "Read More", "View All", "Subscribe", "Contact Us", "About Us",
    }
    items = []
    seen = set()

    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        href = a.get("href", "")
        if not title or title in skip_titles or len(title) < 8:
            continue
        if "/main/" not in href and not href.startswith("/main/"):
            continue
        link = urljoin(url, href)
        if link in seen:
            continue

        container = a.find_parent(["li", "article", "section", "div"]) or a.parent
        text = container.get_text(" ", strip=True) if container else title
        date_match = date_re.search(text)
        published = date_match.group(0) if date_match else ""

        summary = text.replace(title, "", 1).strip()
        if published:
            summary = summary.replace(published, "", 1).strip()
        summary = re.sub(r"\s+", " ", summary)
        summary = summary.replace("Read More", "").strip(" -|")

        items.append({
            "title": title,
            "link": link,
            "published": published,
            "summary": summary[:220],
            "source": "Floor Covering Weekly",
        })
        seen.add(link)
        if len(items) >= limit:
            break

    return items or [{"title": "표시할 FCW 기사를 찾지 못했습니다.", "link": url, "published": "", "summary": "", "source": "FCW"}]


def _get_client(api_key):
    return anthropic.Anthropic(api_key=api_key)


@st.cache_data(ttl=1800)
def analyze_freight_news(api_key, news_items):
    """
    물류/운임 뉴스를 Claude로 분석
    반환: {summary, risk_level, key_factors, llm_comment}
    """
    if not news_items:
        return None

    headlines = "\n".join([f"- {n['title']} ({n['published'][:16]})" for n in news_items])

    prompt = f"""당신은 LVT(럭셔리 비닐 타일) 바닥재를 한국에서 미국으로 수출하는 회사의 물류 분석가입니다.
아래는 최근 해운/물류 관련 뉴스 헤드라인입니다.

{headlines}

이 뉴스들을 바탕으로 다음을 분석해주세요. 반드시 아래 형식의 한국어로 답변하세요:

[위험도] (다음 중 하나: 높음 / 보통 / 낮음)
[핵심요인] (운임에 영향을 주는 핵심 요인 2~3개를 한 줄씩, 간결하게)
[영업코멘트] (LVT 미국 수출 영업 관점에서 지금 무엇을 주의/대비해야 하는지 2~3문장)

분석 시 운임(SCFI/CCFI), 항로 차질, 유가, 컨테이너 수급, 관세 등을 종합적으로 고려하세요."""

    try:
        client = _get_client(api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        return f"⚠️ LLM 분석 오류: {str(e)}"


@st.cache_data(ttl=1800)
def generate_market_briefing(api_key, indicators):
    """
    종합 시장 브리핑 생성
    indicators: dict (모기지금리, 주택착공, CPI, 기준금리, 환율 등)
    """
    ind_text = "\n".join([f"- {k}: {v}" for k, v in indicators.items()])

    prompt = f"""당신은 LVT(럭셔리 비닐 타일) 바닥재를 미국으로 수출하는 한국 회사 해외영업팀의 시장 분석가입니다.
오늘의 주요 경제 지표는 다음과 같습니다:

{ind_text}

위 지표를 종합하여, 해외영업 담당자가 출근하자마자 읽을 "오늘의 시장 브리핑"을 작성하세요.
- 3~4문장으로 간결하게
- LVT 미국 수출 비즈니스 관점에서 해석
- 금리/주택시장이 바닥재 수요에 미치는 영향, 환율이 수익성에 미치는 영향을 짚어주세요
- 전문적이되 읽기 쉬운 한국어로
- 마지막에 한 줄로 "오늘의 액션 포인트"를 제시하세요"""

    try:
        client = _get_client(api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text
    except Exception as e:
        return f"⚠️ 브리핑 생성 오류: {str(e)}"
