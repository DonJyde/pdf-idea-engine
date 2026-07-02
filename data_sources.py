"""
Real trend/demand data connectors for the PDF-guide idea engine.

IMPORTANT — READ BEFORE RUNNING:
This code is written to run against the live internet (Google Trends, Reddit,
Etsy). It will NOT return live data inside this Cowork sandbox, because the
sandbox's outbound network is restricted to an allowlist that excludes these
consumer domains (verified: trends.google.com, reddit.com, and etsy.com all
returned blocked/unreachable during this session). This is not a limitation
of the code — it's a limitation of where it's being run right now.

To get real data, run this on infrastructure with normal outbound internet:
your own laptop, a Vercel/Render/Railway serverless function, or a small
always-on worker (e.g. a $5-7/mo VM or a scheduled cron job). That's how the
production version of the app would run this — server-side, on a schedule,
with results cached in your database so the app's UI never waits on a live
scrape.

Sources used (all free/unofficial tier, matching the MVP data-budget decision):
  1. Google Trends  — via `pytrends` (unofficial wrapper, no API key)
  2. Reddit          — public JSON endpoints (no auth) or PRAW if you register
                        a free Reddit app for higher reliability
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


# ---------------------------------------------------------------------------
# 1. Google Trends — search interest over time for a candidate topic
# ---------------------------------------------------------------------------
def get_trends_interest(keyword: str, timeframe: str = "today 3-m") -> Optional[dict]:
    """
    Returns average and most-recent Google Trends interest (0-100 scale) for
    `keyword` over the given timeframe, plus the trend direction (rising vs
    falling) comparing the first half of the window to the second half.

    Requires: pip install pytrends
    """
    from pytrends.request import TrendReq  # imported lazily so the module
    # still loads even if pytrends isn't installed yet

    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload([keyword], timeframe=timeframe, geo="US")
    df = pytrends.interest_over_time()

    if df.empty:
        return None

    series = df[keyword]
    midpoint = len(series) // 2
    first_half_avg = series.iloc[:midpoint].mean()
    second_half_avg = series.iloc[midpoint:].mean()

    return {
        "keyword": keyword,
        "avg_interest": round(series.mean(), 1),
        "latest_interest": int(series.iloc[-1]),
        "trend_direction": "rising" if second_half_avg > first_half_avg else "falling",
        "momentum_pct": round(
            ((second_half_avg - first_half_avg) / max(first_half_avg, 1)) * 100, 1
        ),
    }


def get_related_rising_queries(keyword: str) -> list[str]:
    """Pulls Google's 'rising related queries' for a seed keyword — this is
    the closest free equivalent to 'what related problem is spiking right
    now', and is a good source of *new* idea candidates, not just scoring
    ideas you already thought of."""
    from pytrends.request import TrendReq

    pytrends = TrendReq(hl="en-US", tz=360)
    pytrends.build_payload([keyword], timeframe="today 3-m", geo="US")
    related = pytrends.related_queries()
    rising_df = related.get(keyword, {}).get("rising")
    if rising_df is None or rising_df.empty:
        return []
    return rising_df["query"].head(10).tolist()


# ---------------------------------------------------------------------------
# 2. Reddit — engagement signal for problem-focused discussion
# ---------------------------------------------------------------------------
def get_reddit_signal(subreddit: str, query: str, limit: int = 25) -> dict:
    """
    Searches a subreddit for `query` and returns aggregate engagement
    (upvotes + comments) as a proxy for how much people are actively
    discussing / struggling with this problem right now.

    Uses Reddit's public JSON search (no auth required, but rate-limited —
    be a good citizen: <=1 request/sec, set a real User-Agent).
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
        "engagement_score": total_score + (total_comments * 2),  # comments > passive upvotes
        "sample_titles": top_titles,
    }


# ---------------------------------------------------------------------------
# 3. Etsy — rough competition/saturation proxy
# ---------------------------------------------------------------------------
def get_etsy_competition(query: str) -> dict:
    """
    Fetches the Etsy search results count for `query` as a directional signal
    for how saturated the topic already is with paid digital products.
    This is a coarse HTML-count heuristic, not an official API — treat the
    number as "low / medium / high" rather than precise, and re-validate
    periodically since Etsy's markup changes.
    """
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
    trend_interest: Optional[dict]
    reddit_signal: Optional[dict]
    etsy_competition: Optional[dict]


def gather_signals(topic: str, subreddit: str) -> IdeaSignal:
    """Pulls all three signals for one candidate topic. Wrapped in try/except
    per-source so one flaky source doesn't kill the whole pipeline — this
    matters because these are unofficial endpoints without an SLA."""
    trend = None
    reddit = None
    etsy = None

    try:
        trend = get_trends_interest(topic)
    except Exception as e:
        print(f"[warn] trends failed for {topic}: {e}")

    try:
        reddit = get_reddit_signal(subreddit, topic)
    except Exception as e:
        print(f"[warn] reddit failed for {topic}: {e}")

    try:
        etsy = get_etsy_competition(topic)
    except Exception as e:
        print(f"[warn] etsy failed for {topic}: {e}")

    time.sleep(1)  # be polite to unauthenticated endpoints
    return IdeaSignal(topic=topic, trend_interest=trend, reddit_signal=reddit, etsy_competition=etsy)


if __name__ == "__main__":
    # Example — will only produce real output when run outside this sandbox.
    signal = gather_signals("freelancer budgeting", subreddit="freelance")
    print(signal)
