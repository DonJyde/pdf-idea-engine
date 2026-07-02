"""
Scheduled trend-refresh job.

Run this on a schedule (GitHub Actions, every 6 hours). It pulls fresh
signals for a watchlist of candidate topics, in each configured region,
scores them, and upserts the results into a Supabase table called `ideas`.
The Streamlit app (app.py) only ever reads from that table, filtered by
the region the user picks, so users never wait on a live scrape.

Environment variables required (GitHub Actions "Secrets"):
    SUPABASE_URL
    SUPABASE_SERVICE_KEY - the service_role/secret key (write access)

See MIGRATION.sql for the ideas table schema, including the geo column.
"""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client

from data_sources import gather_signals, REGIONS
from scoring import score_idea

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

WATCHLIST = [
    {"topic": "freelancer budgeting", "subreddit": "freelance"},
    {"topic": "meal prep for shift workers", "subreddit": "MealPrepSunday"},
    {"topic": "resume rewrite for career changers", "subreddit": "careerguidance"},
    {"topic": "wedding planning checklist", "subreddit": "weddingplanning"},
    {"topic": "budgeting for new parents", "subreddit": "personalfinance"},
    {"topic": "small business bookkeeping basics", "subreddit": "smallbusiness"},
    {"topic": "side hustle ideas for beginners", "subreddit": "sidehustle"},
    {"topic": "study habits for online students", "subreddit": "GetStudying"},
    {"topic": "first apartment moving checklist", "subreddit": "personalfinance"},
    {"topic": "job interview preparation guide", "subreddit": "jobs"},
]

ACTIVE_REGIONS = ["US", "GB", "NG"]


def run():
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    region_lookup = {}
    for r in REGIONS:
        region_lookup[r["code"]] = r["label"]

    results = []

    for geo in ACTIVE_REGIONS:
        for item in WATCHLIST:
            topic = item["topic"]
            sub = item["subreddit"]
            signal = gather_signals(topic, subreddit=sub, geo=geo)
            result = score_idea(topic, signal.trend_interest, signal.reddit_signal, signal.etsy_competition)

            row = {}
            row["topic"] = result.topic
            row["geo"] = geo
            row["geo_label"] = region_lookup.get(geo, geo)
            row["opportunity_score"] = result.opportunity_score
            row["verdict"] = result.verdict
            row["demand_score"] = result.demand_score
            row["momentum_score"] = result.momentum_score
            row["whitespace_score"] = result.whitespace_score
            row["reasons"] = result.reasons
            row["raw_trend"] = signal.trend_interest
            row["raw_reddit"] = signal.reddit_signal
            row["raw_etsy"] = signal.etsy_competition
            row["updated_at"] = datetime.now(timezone.utc).isoformat()

            results.append(row)
            print("[ok]", topic, geo, result.opportunity_score, result.verdict)

    supabase.table("ideas").upsert(results, on_conflict="topic,geo").execute()
    print("Upserted", len(results), "rows (", len(WATCHLIST), "topics x", len(ACTIVE_REGIONS), "regions).")


if __name__ == "__main__":
    run()
