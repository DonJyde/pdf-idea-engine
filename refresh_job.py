"""
Scheduled trend-refresh job.

Run this on a schedule (recommended: GitHub Actions, free tier, e.g. every
6 hours) — NOT inside the Streamlit app itself. It pulls fresh signals for
a watchlist of candidate topics, scores them, and upserts the results into
a Supabase table called `ideas`. The Streamlit app (app.py) only ever
reads from that table, so users never wait on a live scrape and a flaky
source never breaks the live app.

Setup:
    pip install pytrends requests supabase python-dotenv --break-system-packages

Environment variables required (put these in a .env file locally, and in
GitHub Actions "Secrets" when you set up the scheduled workflow):
    SUPABASE_URL       — from your Supabase project settings
    SUPABASE_SERVICE_KEY — the service_role key (NOT the anon key — this
                            script needs write access; the anon key used by
                            app.py should stay read-only)

Supabase table schema (create this once in the Supabase SQL editor):

    create table ideas (
        id bigint generated always as identity primary key,
        topic text not null unique,
        opportunity_score numeric,
        verdict text,
        demand_score numeric,
        momentum_score numeric,
        whitespace_score numeric,
        reasons jsonb,
        raw_trend jsonb,
        raw_reddit jsonb,
        raw_etsy jsonb,
        updated_at timestamptz default now()
    );
"""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from supabase import create_client

from data_sources import gather_signals
from scoring import score_idea

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

# Starter watchlist — expand this over time, or (later) source candidate
# topics automatically from get_related_rising_queries() in data_sources.py
# instead of a fixed list.
WATCHLIST = [
    {"topic": "freelancer budgeting", "subreddit": "freelance"},
    {"topic": "meal prep for shift workers", "subreddit": "MealPrepSunday"},
    {"topic": "resume rewrite for career changers", "subreddit": "careerguidance"},
    {"topic": "wedding planning checklist", "subreddit": "weddingplanning"},
    {"topic": "budgeting for new parents", "subreddit": "personalfinance"},
    {"topic": "small business bookkeeping basics", "subreddit": "smallbusiness"},
]


def run():
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    results = []

    for item in WATCHLIST:
        topic = item["topic"]
        signal = gather_signals(topic, subreddit=item["subreddit"])
        result = score_idea(topic, signal.trend_interest, signal.reddit_signal, signal.etsy_competition)

        row = {
            "topic": result.topic,
            "opportunity_score": result.opportunity_score,
            "verdict": result.verdict,
            "demand_score": result.demand_score,
            "momentum_score": result.momentum_score,
            "whitespace_score": result.whitespace_score,
            "reasons": result.reasons,
            "raw_trend": signal.trend_interest,
            "raw_reddit": signal.reddit_signal,
            "raw_etsy": signal.etsy_competition,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        results.append(row)
        print(f"[ok] {topic}: {result.opportunity_score} ({result.verdict})")

    # upsert on `topic` so re-running just refreshes existing rows
    supabase.table("ideas").upsert(results, on_conflict="topic").execute()
    print(f"Upserted {len(results)} ideas into Supabase.")


if __name__ == "__main__":
    run()
