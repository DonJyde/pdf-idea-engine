"""
Real trend/demand data connectors for the PDF-guide idea engine.

IMPORTANT — READ BEFORE RUNNING:
This code is written to run against the live internet (Google Trends, Reddit,
Etsy). It will NOT return live data inside a sandbox with restricted network
access. Run it on infrastructure with normal outbound internet: your own
laptop, a Vercel/Render/Railway serverless function, or a small always-on
worker (e.g. GitHub Actions, as set up in this project).

Sources used (all free/unofficial tier):
  1. Google Trends  — via `pytrends` (unofficial wrapper, no API key).
                       Supports a `geo` parameter so results can be scoped
                       to a specific country instead of always US.
  2. Reddit          — public JSON endpoints (no auth)
  3. Etsy            — search-results count as a rough "how saturated is this
                        topic already" competition proxy (no official free API
                        for this; treat as directional, not precise)

Install:
    pip install pytrends requests --break-system-packages
"""

from __future__ import annotations
import time
import re
from dataclasses import dataclass
from typing import Optional

import requests

USER_AGENT = "pdf-idea-engine/0.1 (contact: you@yourdomain.com)"

# Common geo codes for the region selector (ISO 3166-1 alpha-2, plus ""
# which pytrends treats as "worldwide"). Add more as needed — this is the
# full list of valid codes: https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2
REGIONS = [
    {"code": "", "label": "Worldwide"},
    {"code": "US", "label": "United States"},
    {"code": "GB", "label": "United Kingdom"},
    {"code": "NG", "label": "Nigeria"},
    {"code": "CA", "label": "Canada"},
    {"code": "AU", "label": "Australia"},
    {"code": "IN", "label": "India"},
    {"code": "ZA", "label": "South Africa"},
]


# ---------------------------------------------------------------------------
# 1. Google Trends — search interest over time for a candidate topic
# ---------------------------------------------------------------------------
def get_trends_interest(keyword: str, timeframe: str = "today 3-m", geo: str = "US") -> Optional[dict]:
    """
    Returns average and most-recent Google Trends interest (0-100 scale) for
    `keyword` over the given timeframe and region, plus the trend direction
    (rising vs falling) comparing the first half of the window to the second.

    `geo` is an ISO country code (e.g. "US", "GB", "NG") or "" for worldwide.
    """
    from pytrends.request import TrendReq  # imported lazily so the module
    # still loads even if pytrends isn't installed yet

    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload([keyword], timeframe=timeframe, geo=geo)
    df = pytrends.interest_over_time()

    if df.empty:
        return None

    series = df[keyword]
    midpoint = len(series) // 2
    first_half_avg = series.iloc[:midpoint].mean()
    second_half_avg = series.iloc[midpoint:].mean()

    return {
        "keyword": keyword,
        "geo": geo,
        "avg_interest": round(series.mean(), 1),
        "latest_interest": int(series.iloc[-1]),
        "trend_direction": "rising" if second_half_avg > first_half_avg else "falling",
        "momentum_pct": round(
            ((second_half_avg - first_half_avg) / max(first_half_avg, 1)) * 100, 1
        ),
    }


def get_related_rising_queries(keyword: str, geo: str = "US") -> list[str]:
    """Pulls Google's 'rising related queries' for a seed keyword, scoped to
    `geo`. Closest free equivalent to 'what related problem is spiking right
    now' — a good source of *new* idea candidates, not just scoring ideas
    you already thought of."""
    from pytrends.request import TrendReq

    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload([keyword], timeframe="today 3-m", geo=geo)
    related = pytrends.related_queries()
    rising_df = related.get(keyword, {}).get("rising")
    if rising_df is None or rising_df.empty:
        return []
    return rising_df["query"].head(10).tolist()


# ---------------------------------------------------------------------------
# 2. Reddit — engagement signal for problem-focused discussion
#    (Reddit's public search has no region concept, so this stays global)
# ---------------------------------------------------------------------------
def get_reddit_signal(subreddit: str, query: str, limit: int = 25) -> dict:
    """
    Searches a subreddit for `query` and returns aggregate engagement
    (upvotes + comments) as a proxy for how much people are actively
    discussing / struggling with this problem right now.
    """
    url = f"https://www.reddit.com/r/{subreddit}/search.json"
    params = {"q": query, "restrict_sr": "on", "sort": "top", "t": "month", "limit": limit}
    resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=10)
    resp.raise_for_status()
    posts = resp.json()["data"]["children"]

    total_score = sum(p["data"]["score"] for p in posts)
    total_comments = sum(p["data"]["num_comments"] for p in posts)
    top_titles = [p["data"]["title"] for p in posts[:5]]

    return {
        "subreddit": subreddit,
        "query": query,
        "post_count": len(posts),
        "total_upvotes": total_score,
        "total_comments": total_comments,
        "engagement_score": total_score + (total_comments * 2),
        "sample_titles": top_titles,
    }


# ---------------------------------------------------------------------------
# 3. Etsy — rough competition/saturation proxy
#    (Etsy's search doesn't reliably geo-filter for unauthenticated
#    requests, so this also stays global)
# ---------------------------------------------------------------------------
def get_etsy_competition(query: str) -> dict:
    url = "https://www.etsy.com/search"
    params = {"q": query, "explicit": "1"}
    resp = requests.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=10)
    resp.raise_for_status()

    match = re.search(r'"total_results":\s*(\d+)', resp.text)
    result_count = int(match.group(1)) if match else None

    if result_count is None:
        saturation = "unknown"
    elif result_count < 500:
        saturation = "low"
    elif result_count < 5000:
        saturation = "medium"
    else:
        saturation = "high"

    return {"query": query, "listing_count": result_count, "saturation": saturation}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
@dataclass
class IdeaSignal:
    topic: str
    geo: str
    trend_interest: Optional[dict]
    reddit_signal: Optional[dict]
    etsy_competition: Optional[dict]


def gather_signals(topic: str, subreddit: str, geo: str = "US") -> IdeaSignal:
    """Pulls all three signals for one candidate topic in one region. Wrapped
    in try/except per-source so one flaky source doesn't kill the whole
    pipeline — these are unofficial endpoints without an SLA."""
    trend = None
    reddit = None
    etsy = None

    try:
        trend = get_trends_interest(topic, geo=geo)
    except Exception as e:
        print(f"[warn] trends failed for {topic} ({geo}): {e}")

    try:
        reddit = get_reddit_signal(subreddit, topic)
    except Exception as e:
        print(f"[warn] reddit failed for {topic}: {e}")

    try:
        etsy = get_etsy_competition(topic)
    except Exception as e:
        print(f"[warn] etsy failed for {topic}: {e}")

    time.sleep(1)  # be polite to unauthenticated endpoints
    return IdeaSignal(topic=topic, geo=geo, trend_interest=trend, reddit_signal=reddit, etsy_competition=etsy)


if __name__ == "__main__":
    signal = gather_signals("freelancer budgeting", subreddit="freelance", geo="US")
    print(signal)
