"""
Real trend/demand data connectors for the PDF-guide idea engine.

v2 change: Reddit and Etsy switched from anonymous scraping to authenticated
official APIs. Running the original scraping approach from GitHub Actions'
shared IP ranges got blocked on every single request (429 from Google
Trends, 403 from Reddit and Etsy) - cloud CI IP ranges are aggressively
blocklisted by anti-bot systems in a way a normal residential connection
usually isn't. Authenticated requests are far more resistant to that.

Sources used:
  1. Google Trends - via `pytrends` (unofficial, no key). Still anonymous -
     there is no free authenticated alternative. Expect this one to keep
     failing intermittently on cloud infrastructure; it degrades gracefully
     (falls back to a neutral momentum score) rather than crashing.
  2. Reddit         - official OAuth API via `praw`. Requires a free Reddit
     "script" app (client_id + client_secret) registered at
     reddit.com/prefs/apps.
  3. Etsy           - official Open API v3, keyword search on active
     listings. Requires a free Etsy developer API key registered at
     developers.etsy.com. No OAuth needed for this specific endpoint, just
     the API key in a header.

Install:
    pip install pytrends requests praw --break-system-packages

Environment variables required:
    REDDIT_CLIENT_ID
    REDDIT_CLIENT_SECRET
    REDDIT_USER_AGENT   (any descriptive string, e.g. "pdf-idea-engine/0.2 by u/yourname")
    ETSY_API_KEY
"""

from __future__ import annotations
import os
import time
from dataclasses import dataclass
from typing import Optional

import requests

USER_AGENT = "pdf-idea-engine/0.2 (contact: you@yourdomain.com)"

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
# 1. Google Trends - search interest over time for a candidate topic
# ---------------------------------------------------------------------------
def get_trends_interest(keyword: str, timeframe: str = "today 3-m", geo: str = "US") -> Optional[dict]:
    from pytrends.request import TrendReq

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
    from pytrends.request import TrendReq

    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload([keyword], timeframe="today 3-m", geo=geo)
    related = pytrends.related_queries()
    rising_df = related.get(keyword, {}).get("rising")
    if rising_df is None or rising_df.empty:
        return []
    return rising_df["query"].head(10).tolist()


# ---------------------------------------------------------------------------
# 2. Reddit - official OAuth API via PRAW
# ---------------------------------------------------------------------------
def _get_reddit_client():
    import praw

    return praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get("REDDIT_USER_AGENT", USER_AGENT),
    )


def get_reddit_signal(subreddit: str, query: str, limit: int = 25) -> dict:
    """
    Searches a subreddit for `query` via Reddit's authenticated API and
    returns aggregate engagement (upvotes + comments) as a proxy for how
    much people are actively discussing this problem right now.
    """
    reddit = _get_reddit_client()
    posts = list(reddit.subreddit(subreddit).search(query, sort="top", time_filter="month", limit=limit))

    total_score = sum(p.score for p in posts)
    total_comments = sum(p.num_comments for p in posts)
    top_titles = [p.title for p in posts[:5]]

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
# 3. Etsy - official Open API v3, active listings keyword search
# ---------------------------------------------------------------------------
def get_etsy_competition(query: str) -> dict:
    """
    Uses Etsy's official Open API v3 to count active listings matching
    `query`, as a directional signal for how saturated the topic already is
    with paid digital products. Requires only an API key (no OAuth) for
    this endpoint.
    """
    api_key = os.environ["ETSY_API_KEY"]
    url = "https://api.etsy.com/v3/application/listings/active"
    params = {"keywords": query, "limit": 25}
    resp = requests.get(url, params=params, headers={"x-api-key": api_key}, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    result_count = data.get("count")
    if result_count is None:
        result_count = len(data.get("results", []))

    if result_count < 500:
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
    trend = None
    reddit_sig = None
    etsy = None

    try:
        trend = get_trends_interest(topic, geo=geo)
    except Exception as e:
        print(f"[warn] trends failed for {topic} ({geo}): {e}")

    try:
        reddit_sig = get_reddit_signal(subreddit, topic)
    except Exception as e:
        print(f"[warn] reddit failed for {topic}: {e}")

    try:
        etsy = get_etsy_competition(topic)
    except Exception as e:
        print(f"[warn] etsy failed for {topic}: {e}")

    time.sleep(1)
    return IdeaSignal(topic=topic, geo=geo, trend_interest=trend, reddit_signal=reddit_sig, etsy_competition=etsy)


if __name__ == "__main__":
    signal = gather_signals("freelancer budgeting", subreddit="freelance", geo="US")
    print(signal)
