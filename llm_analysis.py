"""
llm_analysis.py
LVT Intelligence Dashboard — LLM 분석 모듈
- 무역/물류 뉴스를 RSS로 수집
- Claude API로 분석 (뉴스 요약 + 시장 브리핑)
"""

import feedparser
import anthropic
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import streamlit as st
from urllib.parse import urljoin, urlparse
import re

# ── 뉴스 RSS 피드 (모두 무료, Google News 기반) ─────────────────
NEWS_FEEDS = {
    "freight": "https://news.google.com/rss/search?q=container+freight+shipping+rate+SCFI&hl=en-US&gl=US&ceid=US:en",
    "tariff":  "https://news.google.com/rss/search?q=US+tariff+import+flooring+vinyl&hl=en-US&gl=US&ceid=US:en",
    "housing": "https://news.google.com/rss/search?q=US+housing+market+mortgage+construction&hl=en-US&gl=US&ceid=US:en",
    "kcc_glass": "https://news.google.com/rss/search?q=%22KCC%EA%B8%80%EB%9D%BC%EC%8A%A4%22&hl=ko&gl=KR&ceid=KR:ko",
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

FCNEWS_URLS = {
    "Home": "https://www.fcnews.net/",
    "Resilient": "https://www.fcnews.net/category/news/resilient/",
    "Wood": "https://www.fcnews.net/category/news/wood/",
    "Tile": "https://www.fcnews.net/category/news/tile/",
    "Carpet": "https://www.fcnews.net/category/news/carpet/",
    "Technology": "https://www.fcnews.net/category/news/technology/",
    "Laminate": "https://www.fcnews.net/category/news/laminate/",
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
    fetched_at = datetime.now().astimezone().isoformat(timespec="seconds")
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
        "Content Categories", "Media Kit", "Classifieds", "Latest", "Floor Covering Weekly",
    }
    items = []
    seen = set()

    def pick_image(container):
        if not container:
            return ""
        img = container.find("img")
        if not img:
            return ""
        for attr in ["data-src", "data-original", "data-lazy-src", "src"]:
            src = img.get(attr)
            if src and not src.startswith("data:"):
                return urljoin(url, src)
        srcset = img.get("srcset", "")
        if srcset:
            first = srcset.split(",")[0].strip().split(" ")[0]
            return urljoin(url, first)
        return ""

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
        if summary in skip_titles:
            summary = ""

        items.append({
            "title": title,
            "link": link,
            "published": published,
            "summary": summary[:220],
            "image": pick_image(container),
            "category": category,
            "source": "Floor Covering Weekly",
            "_fetched_at": fetched_at,
            "_source_url": url,
        })
        seen.add(link)
        if len(items) >= limit:
            break

    return items or [{"title": "표시할 FCW 기사를 찾지 못했습니다.", "link": url, "published": "", "summary": "", "source": "FCW"}]


@st.cache_data(ttl=1800)
def fetch_fcnews_news(category="Home", limit=12):
    """Floor Covering News(fcnews.net) latest article list."""
    url = FCNEWS_URLS.get(category, FCNEWS_URLS["Home"])
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
        )
    }
    fetched_at = datetime.now().astimezone().isoformat(timespec="seconds")
    try:
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        return [{"title": "FCNews 기사를 불러오지 못했습니다.", "link": url, "published": "", "summary": str(e), "image": "", "category": category, "source": "Floor Covering News"}]

    skip_titles = {
        "News", "Categories", "Category", "Videos", "Classifieds", "Archives",
        "Advertise", "Subscribe", "Read more", "View More +", "More", "Search",
        "Current Issue", "Supplements", "Events", "Featured articles",
    }
    article_re = re.compile(r"/\d{4}/\d{2}/\d{2}/")
    items = []
    seen = set()

    def pick_image(container):
        if not container:
            return ""
        img = container.find("img")
        if not img:
            return ""
        for attr in ["data-src", "data-lazy-src", "src"]:
            src = img.get(attr)
            if src and not src.startswith("data:"):
                return urljoin(url, src)
        srcset = img.get("srcset", "")
        if srcset:
            first = srcset.split(",")[0].strip().split(" ")[0]
            return urljoin(url, first)
        return ""

    def clean_summary(container, title):
        if not container:
            return ""
        text = container.get_text(" ", strip=True)
        text = text.replace(title, "", 1)
        text = re.sub(r"Read more.*", "", text, flags=re.I)
        text = re.sub(r"\s+", " ", text).strip(" -|")
        return text[:220]

    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        href = a.get("href", "")
        if not title or title in skip_titles or len(title) < 10:
            continue
        link = urljoin(url, href)
        if not article_re.search(link) or link in seen:
            continue
        container = a.find_parent(["article", "div", "li", "section"]) or a.parent
        text = container.get_text(" ", strip=True) if container else title
        date_match = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}", text)
        published = date_match.group(0) if date_match else ""
        items.append({
            "title": title,
            "link": link,
            "published": published,
            "summary": clean_summary(container, title),
            "image": pick_image(container),
            "category": category,
            "source": "Floor Covering News",
            "_fetched_at": fetched_at,
            "_source_url": url,
        })
        seen.add(link)
        if len(items) >= limit:
            break

    return items or [{"title": "표시할 FCNews 기사를 찾지 못했습니다.", "link": url, "published": "", "summary": "", "image": "", "category": category, "source": "Floor Covering News"}]


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


# Public article extraction and governed executive synthesis.
# Article collection uses normal HTTP/HTML parsing; the LLM is applied only
# after the source body and platform indicator dates have been captured.
ARTICLE_DOMAINS = {
    "floorcoveringweekly.com",
    "www.floorcoveringweekly.com",
    "fcnews.net",
    "www.fcnews.net",
}

MARKET_ARTICLE_KEYWORDS = (
    "resilient", "lvt", "vinyl", "flooring", "housing", "residential",
    "remodel", "construction", "demand", "sales", "orders", "inventory",
    "supply", "domestic", "retail", "builder", "commercial", "mortgage",
)


def _article_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }


def _meta_content(soup, *selectors):
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            value = node.get("content") or node.get("datetime") or node.get_text(" ", strip=True)
            if value:
                return re.sub(r"\s+", " ", value).strip()
    return ""


@st.cache_data(ttl=1800)
def fetch_article_content(url):
    """Fetch a public FCW/FCNews article and return its readable body."""
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in ARTICLE_DOMAINS:
        return {"ok": False, "url": str(url or ""), "error": "Only public FCW and FCNews article URLs are supported."}

    try:
        response = requests.get(url, headers=_article_headers(), timeout=18)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as exc:
        return {"ok": False, "url": url, "error": f"Article request failed: {exc}"}

    title = _meta_content(soup, 'meta[property="og:title"]', 'meta[name="twitter:title"]', "h1")
    description = _meta_content(
        soup,
        'meta[property="og:description"]',
        'meta[name="description"]',
        'meta[name="twitter:description"]',
    )
    published = _meta_content(
        soup,
        'meta[property="article:published_time"]',
        'meta[name="date"]',
        'meta[name="publish-date"]',
        "time[datetime]",
        "time",
    )
    author = _meta_content(soup, 'meta[name="author"]', '[rel="author"]', ".author", ".byline")
    page_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    if not published:
        date_match = re.search(
            r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+"
            r"\d{1,2},\s+\d{4}",
            page_text,
            flags=re.I,
        )
        published = date_match.group(0) if date_match else ""
    if not author:
        author_match = re.search(r"\bBy\s+([A-Z][A-Za-z.' -]{2,50})\s+(?=[A-Z])", page_text)
        author = author_match.group(1).strip() if author_match else ""

    # FCW wraps the page in an ASP.NET form, so removing all form nodes would
    # also delete the article itself.
    for node in soup.select("script, style, noscript, nav, header, footer, aside"):
        node.decompose()

    candidates = []
    for selector in (
        "article", '[itemprop="articleBody"]', ".article-body", ".article-content",
        ".story-body", ".entry-content", ".post-content", ".news-detail",
        ".body-copy", ".page-content.mod-details", "main",
    ):
        for container in soup.select(selector):
            paragraphs = []
            for paragraph in container.find_all(["p", "h2", "h3"], recursive=True):
                text = re.sub(r"\s+", " ", paragraph.get_text(" ", strip=True)).strip()
                if len(text) >= 35 and not re.search(r"subscribe|newsletter|advertis|copyright", text, re.I):
                    paragraphs.append(text)
            # FCW currently places article copy inside a div with line breaks
            # instead of semantic paragraph tags.
            if not paragraphs and (
                container.select_one(".body-copy") is not None
                or "body-copy" in (container.get("class") or [])
            ):
                text = re.sub(r"\s+", " ", container.get_text(" ", strip=True)).strip()
                if len(text) >= 350:
                    paragraphs.append(text)
            body = "\n".join(dict.fromkeys(paragraphs))
            if body:
                candidates.append(body)

    body = max(candidates, key=len, default="")
    if len(body) < 350:
        fallback = []
        for paragraph in soup.find_all("p"):
            text = re.sub(r"\s+", " ", paragraph.get_text(" ", strip=True)).strip()
            if len(text) >= 45 and not re.search(r"subscribe|newsletter|advertis|copyright", text, re.I):
                fallback.append(text)
        body = "\n".join(dict.fromkeys(fallback))

    if len(body) < 350:
        return {
            "ok": False,
            "url": url,
            "title": title,
            "published": published,
            "error": "The public article body could not be extracted reliably.",
        }

    return {
        "ok": True,
        "url": url,
        "title": title or parsed.path.rstrip("/").split("/")[-1].replace("-", " ").title(),
        "published": published,
        "author": author,
        "description": description,
        "text": body[:18000],
        "source": "Floor Covering Weekly" if "floorcoveringweekly" in parsed.netloc else "Floor Covering News",
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _market_relevance(item):
    title = str(item.get("title") or "").lower()
    haystack = f"{title} {item.get('summary', '')}".lower()
    return sum(3 if keyword in title else 1 for keyword in MARKET_ARTICLE_KEYWORDS if keyword in haystack)


@st.cache_data(ttl=1800)
def collect_fcw_market_articles(primary_url, limit=4):
    """Collect one selected FCW article plus a few current, relevant FCW articles."""
    articles = []
    errors = []
    primary = fetch_article_content(primary_url)
    if primary.get("ok"):
        primary["role"] = "Primary article"
        articles.append(primary)
    else:
        errors.append(primary.get("error", "Primary article could not be read."))

    candidates = []
    seen = {str(primary_url).rstrip("/")}
    for category in ("Features", "Retail", "Business Builder", "All Latest"):
        for item in fetch_fcw_news(category, limit=12):
            link = str(item.get("link") or "").rstrip("/")
            relevance = _market_relevance(item)
            if not link or link in seen or relevance <= 0:
                continue
            seen.add(link)
            candidates.append((relevance, item))

    candidates.sort(key=lambda pair: pair[0], reverse=True)
    for _, item in candidates:
        if len(articles) >= max(1, min(int(limit), 6)):
            break
        article = fetch_article_content(item.get("link"))
        if article.get("ok"):
            article["role"] = "Related current article"
            articles.append(article)

    return {"ok": bool(articles and primary.get("ok")), "articles": articles, "errors": errors}


def _extract_json_object(text):
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("The model did not return a JSON object.")
    return json.loads(cleaned[start:end + 1])


def _indicator_change(indicators, label):
    item = dict((indicators or {}).get(label) or {})
    match = re.search(r"([+-]\d+(?:\.\d+)?)\s*%", str(item.get("change") or ""))
    return float(match.group(1)) if match else None


def _indicator_sentence(indicators, labels):
    parts = []
    for label in labels:
        item = dict((indicators or {}).get(label) or {})
        if not item:
            continue
        parts.append(
            f"{label} {item.get('latest', 'N/A')} "
            f"({item.get('change', 'change N/A')}, as of {item.get('data_as_of', 'N/A')})"
        )
    return "; ".join(parts) or "직접 비교 가능한 지표가 없습니다."


def _article_topic_count(articles, terms):
    text = " ".join(str(article.get("text") or "").lower() for article in articles or [])
    return sum(len(re.findall(rf"\b{re.escape(term.lower())}\b", text)) for term in terms)


def _topic_evidence(articles, label, terms):
    hits = _article_topic_count(articles, terms)
    article_count = len(articles or [])
    if hits:
        return f"수집 기사 {article_count}건에서 {label} 관련 표현이 {hits}회 확인됩니다."
    return f"수집 기사 {article_count}건에서는 {label} 관련 직접 표현이 제한적입니다."


def _fallback_reason_text(error):
    text = str(error or "").lower()
    if "credit balance" in text or "billing" in text:
        return "Anthropic API credit unavailable"
    if "authentication" in text or "api key" in text or "401" in text:
        return "Anthropic API authentication unavailable"
    if "rate limit" in text or "429" in text:
        return "Anthropic API rate limit"
    if "timeout" in text or "connection" in text:
        return "Anthropic API connection unavailable"
    return "Anthropic API response unavailable"


def rule_based_resilient_market_analysis(articles, indicators, reason="Anthropic API unavailable"):
    """Build a transparent, deterministic fallback from article topics and indicator directions."""
    valid_articles = [article for article in (articles or []) if article.get("ok") and article.get("text")]
    if not valid_articles:
        return {"ok": False, "error": "No verified article body is available for fallback analysis."}

    changes = {
        label: _indicator_change(indicators, label)
        for label in (
            "Housing Starts", "Building Permits", "Existing Sales", "Monthly Supply",
            "30Y Mortgage", "Building Retail", "New Home Sales", "Housing Completions",
        )
    }

    pressure_score = 0
    for label in ("Housing Starts", "Building Permits", "Existing Sales", "Building Retail", "New Home Sales"):
        value = changes.get(label)
        if value is not None:
            pressure_score += -1 if value < 0 else 1 if value > 0 else 0
    for label in ("Monthly Supply", "30Y Mortgage"):
        value = changes.get(label)
        if value is not None:
            pressure_score += -1 if value > 0 else 1 if value < 0 else 0

    negative_terms = ("slow", "soft", "decline", "weak", "pressure", "cautious", "uncertain", "downturn")
    positive_terms = ("steady", "stable", "strong", "improve", "growth", "recovery")
    article_balance = min(_article_topic_count(valid_articles, positive_terms), 3) - min(
        _article_topic_count(valid_articles, negative_terms), 3
    )
    combined_score = pressure_score + (1 if article_balance > 0 else -1 if article_balance < 0 else 0)

    if combined_score <= -4:
        status = "압박"
        headline = "주택·금융·유통 지표가 Resilient 주문 환경에 복합적인 하방 압력을 나타냅니다."
    elif combined_score <= -2:
        status = "둔화"
        headline = "미국 주거 수요와 유통 신호가 약해 Resilient 주문 회복은 제한적으로 보입니다."
    elif combined_score >= 4:
        status = "회복"
        headline = "주택 및 유통 지표가 개선되며 Resilient 주문 환경에 회복 신호가 나타납니다."
    elif combined_score >= 2:
        status = "안정화"
        headline = "일부 수요 지표가 개선되지만 Resilient 주문 회복 여부는 추가 확인이 필요합니다."
    else:
        status = "혼조"
        headline = "미국 내 공급과 수요 지표가 엇갈려 Resilient 주문 환경은 혼조로 판단됩니다."

    available_changes = sum(value is not None for value in changes.values())
    confidence = "보통" if len(valid_articles) >= 2 and available_changes >= 5 else "낮음"

    starts = changes.get("Housing Starts")
    permits = changes.get("Building Permits")
    existing = changes.get("Existing Sales")
    retail = changes.get("Building Retail")
    mortgage = changes.get("30Y Mortgage")
    supply = changes.get("Monthly Supply")

    residential_status = "weak" if sum(
        value < 0 for value in (existing, retail) if value is not None
    ) >= 1 or (mortgage is not None and mortgage > 0) else "mixed"
    builder_values = [value for value in (starts, permits) if value is not None]
    builder_status = (
        "weak" if builder_values and all(value < 0 for value in builder_values)
        else "stable" if builder_values and all(value > 0 for value in builder_values)
        else "mixed"
    )

    demand_evidence = _topic_evidence(
        valid_articles, "housing·residential·remodel 수요",
        ("housing", "residential", "remodel", "demand", "sales", "orders"),
    )
    finance_evidence = _topic_evidence(
        valid_articles, "금리·구매여력",
        ("mortgage", "rate", "rates", "affordability", "financing"),
    )
    inventory_evidence = _topic_evidence(
        valid_articles, "재고·공급·미국 내 생산",
        ("inventory", "supply", "domestic", "manufacturing", "production"),
    )
    channel_evidence = _topic_evidence(
        valid_articles, "유통·리테일 채널",
        ("retail", "dealer", "distributor", "channel", "sell-through"),
    )

    summary = [
        (
            f"수요 지표 방향 점수는 {pressure_score:+d}이며, "
            f"{_indicator_sentence(indicators, ['Existing Sales', 'Building Retail'])}를 함께 확인했습니다."
        ),
        (
            f"신규 주택 파이프라인은 "
            f"{_indicator_sentence(indicators, ['Housing Starts', 'Building Permits', 'Housing Completions'])}로 "
            "지표 간 방향 일치 여부를 구분해 봐야 합니다."
        ),
        (
            f"기사에서는 공급·수요 주제가 함께 나타나지만, 공급 안정이 최종 수요 회복을 의미하지는 않습니다. "
            f"현재 분석은 {reason}에 따른 규칙 기반 대체 판정입니다."
        ),
    ]

    return {
        "ok": True,
        "analysis_mode": "Rule-based fallback",
        "fallback_reason": reason,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": status,
        "confidence": confidence,
        "headline": headline,
        "executive_summary": summary,
        "drivers": [
            {
                "driver": "주택·리모델 수요",
                "direction": "negative" if residential_status == "weak" else "neutral",
                "article_evidence": demand_evidence,
                "indicator_evidence": _indicator_sentence(
                    indicators, ["Existing Sales", "Building Retail", "New Home Sales"]
                ),
                "implication": "주거·리모델 채널의 보충 주문 속도를 보수적으로 점검해야 합니다.",
            },
            {
                "driver": "금융 여건",
                "direction": "negative" if mortgage is not None and mortgage > 0 else "neutral",
                "article_evidence": finance_evidence,
                "indicator_evidence": _indicator_sentence(indicators, ["30Y Mortgage"]),
                "implication": "금리 방향과 기존주택 거래 회복이 동시에 나타나는지 확인해야 합니다.",
            },
            {
                "driver": "재고·공급",
                "direction": "negative" if supply is not None and supply > 0 else "neutral",
                "article_evidence": inventory_evidence,
                "indicator_evidence": _indicator_sentence(indicators, ["Monthly Supply"]),
                "implication": "공급 안정과 수요 회복을 분리하고 유통 재고 조정 여부를 확인해야 합니다.",
            },
            {
                "driver": "유통 채널",
                "direction": "negative" if retail is not None and retail < 0 else "neutral",
                "article_evidence": channel_evidence,
                "indicator_evidence": _indicator_sentence(indicators, ["Building Retail"]),
                "implication": "출하보다 실제 sell-through와 재주문 시점을 함께 점검해야 합니다.",
            },
        ],
        "channels": [
            {
                "channel": "Residential / Remodel",
                "status": residential_status,
                "read": "기존주택판매·모기지·건자재 유통매출을 함께 본 규칙 기반 판정입니다.",
            },
            {
                "channel": "Builder / New Construction",
                "status": builder_status,
                "read": "착공·허가·완공의 방향 일치 여부를 기준으로 판단했습니다.",
            },
            {
                "channel": "Commercial",
                "status": "mixed",
                "read": "플랫폼에 직접 대응하는 상업용 수요 지표가 없어 기사 언급 범위만 참고합니다.",
            },
        ],
        "order_gap_explanation": [
            "높은 금융비용과 느린 주택 회전이 리모델링 의사결정을 늦출 수 있습니다.",
            "유통 채널의 재고 보수 운영이 최종 수요보다 주문 감소폭을 키울 수 있습니다.",
            "미국 내 공급 안정 또는 확대가 수입 제품의 주문 경쟁에 영향을 줄 수 있습니다.",
        ],
        "watch_items": [
            "기존주택판매와 30년 모기지 금리의 동시 개선 여부",
            "건자재 유통매출과 실제 sell-through의 회복 여부",
            "신규주택 재고개월 및 유통 재고 조정 종료 신호",
        ],
        "contradictions": [
            "기사의 공급 안정 신호와 거시 수요 회복은 동일한 의미가 아닙니다.",
            "상업용 채널은 직접 대응하는 정량 지표가 부족합니다.",
        ],
        "caveat": (
            "공개 기사 키워드와 거시지표 방향을 이용한 규칙 기반 판정이며, "
            "자사 수주 감소의 직접 인과나 수요 전망을 확정하지 않습니다."
        ),
    }


def analyze_resilient_market_articles(api_key, articles, indicators):
    """Synthesize article evidence and live indicators into a governed executive readout."""
    valid_articles = [article for article in (articles or []) if article.get("ok") and article.get("text")]
    if not valid_articles:
        return {"ok": False, "error": "No verified article body is available for analysis."}
    if not api_key:
        return rule_based_resilient_market_analysis(
            valid_articles,
            indicators,
            reason="ANTHROPIC_API_KEY not configured",
        )

    evidence_blocks = []
    for index, article in enumerate(valid_articles[:5], 1):
        evidence_blocks.append(
            "\n".join([
                f"ARTICLE {index}",
                f"Title: {article.get('title', '')}",
                f"Source: {article.get('source', '')}",
                f"Published: {article.get('published', '') or 'Not stated'}",
                f"URL: {article.get('url', '')}",
                "Body:",
                str(article.get("text", ""))[:9000],
            ])
        )

    prompt = f"""You are preparing an internal executive brief for a Korean LVT export sales team.
Analyze the public flooring-industry articles and the platform indicators below to explain current U.S. domestic demand and resilient-flooring order conditions.

GOVERNANCE RULES
- Write every reader-facing field in concise, professional Korean.
- Do not invent facts, dates, quotations, causal claims, or numbers.
- Treat articles as qualitative industry evidence, not as a statistical sample.
- Treat indicators as directional evidence. Do not claim that they prove KCC order causality.
- Separate confirmed alignment, disagreement, and residual uncertainty.
- If evidence conflicts, say so explicitly.
- Avoid sales promises, forecasts, and unsupported recommendations.

PLATFORM INDICATORS (JSON)
{json.dumps(indicators or {}, ensure_ascii=False, default=str)}

PUBLIC ARTICLE EVIDENCE
{chr(10).join(evidence_blocks)}

Return JSON only with this exact shape:
{{
  "status": "압박|둔화|혼조|안정화|회복",
  "confidence": "낮음|보통|높음",
  "headline": "one answer-first sentence",
  "executive_summary": ["2-3 concise bullets"],
  "drivers": [
    {{"driver": "Demand or channel driver", "direction": "negative|neutral|positive", "article_evidence": "what articles support", "indicator_evidence": "what indicators support or contradict", "implication": "so what for resilient orders"}}
  ],
  "channels": [
    {{"channel": "Residential / Remodel|Builder / New Construction|Commercial", "status": "weak|mixed|stable|firm", "read": "concise evidence-based read"}}
  ],
  "order_gap_explanation": ["up to 3 evidence-based explanations"],
  "watch_items": ["3 monitoring points with no forecast"],
  "contradictions": ["evidence gaps or conflicts"],
  "caveat": "one concise limitation statement"
}}
"""

    try:
        client = _get_client(api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2400,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        result = _extract_json_object(message.content[0].text)
        required = {"status", "confidence", "headline", "executive_summary", "drivers", "channels", "watch_items", "caveat"}
        missing = sorted(required.difference(result))
        if missing:
            raise ValueError(f"Missing analysis fields: {', '.join(missing)}")
        result["ok"] = True
        result["analysis_mode"] = "Claude LLM"
        result["generated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        return result
    except Exception as exc:
        return rule_based_resilient_market_analysis(
            valid_articles,
            indicators,
            reason=_fallback_reason_text(exc),
        )
