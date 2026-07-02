"""
Opportunity Score — turns raw signals from data_sources.py into a single
0-100 number a non-technical user can act on, plus the human-readable
"why" behind it (this matters: a score with no explanation is just a new
version of "trust the AI", which is the exact complaint leveled at the
product we're improving on).

Formula (v1 — tune with real usage data once live):

    opportunity_score = (
          0.40 * demand_score        # is anyone looking for this?
        + 0.30 * momentum_score      # is it growing or fading?
        + 0.30 * whitespace_score    # is it already crowded with paid products?
    )

Each sub-score is normalized 0-100 before weighting.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class OpportunityResult:
    topic: str
    demand_score: float
    momentum_score: float
    whitespace_score: float
    opportunity_score: float
    verdict: str
    reasons: list[str] = field(default_factory=list)


def _demand_score(trend_interest: Optional[dict], reddit_signal: Optional[dict]) -> float:
    """Blends Google Trends interest (0-100 already) with normalized Reddit
    engagement. If one source is missing (flaky unofficial API), fall back
    to the other rather than zeroing the whole score."""
    trend_component = trend_interest["avg_interest"] if trend_interest else None
    reddit_component = None
    if reddit_signal:
        # crude normalization: 500+ combined engagement in a month = "hot" (100)
        reddit_component = min(100, (reddit_signal["engagement_score"] / 500) * 100)

    parts = [p for p in (trend_component, reddit_component) if p is not None]
    return sum(parts) / len(parts) if parts else 0.0


def _momentum_score(trend_interest: Optional[dict]) -> float:
    if not trend_interest:
        return 50.0  # neutral if unknown, don't punish missing data
    momentum_pct = trend_interest["momentum_pct"]
    # map -100%..+100% momentum onto a 0-100 score, centered at 50
    return max(0.0, min(100.0, 50 + momentum_pct / 2))


def _whitespace_score(etsy_competition: Optional[dict]) -> float:
    """Inverted: LOW existing paid-product saturation = HIGH whitespace score.
    This is the piece the original product never measured at all — it told
    you what's popular without telling you if 40 other guides already exist
    for the exact same topic."""
    if not etsy_competition or etsy_competition["saturation"] == "unknown":
        return 50.0
    return {"low": 90.0, "medium": 55.0, "high": 20.0}[etsy_competition["saturation"]]


def score_idea(topic: str, trend_interest, reddit_signal, etsy_competition) -> OpportunityResult:
    demand = _demand_score(trend_interest, reddit_signal)
    momentum = _momentum_score(trend_interest)
    whitespace = _whitespace_score(etsy_competition)

    overall = round(0.40 * demand + 0.30 * momentum + 0.30 * whitespace, 1)

    if overall >= 70:
        verdict = "Strong opportunity"
    elif overall >= 45:
        verdict = "Worth testing"
    else:
        verdict = "Skip — weak or oversaturated"

    reasons = []
    if trend_interest:
        reasons.append(
            f"Search interest is {trend_interest['trend_direction']} "
            f"({trend_interest['momentum_pct']:+.0f}% over the window)."
        )
    if reddit_signal:
        reasons.append(
            f"{reddit_signal['post_count']} recent Reddit threads, "
            f"{reddit_signal['total_comments']} comments — real people actively discussing this problem."
        )
    if etsy_competition and etsy_competition["listing_count"] is not None:
        reasons.append(
            f"{etsy_competition['listing_count']} existing Etsy listings for this topic "
            f"({etsy_competition['saturation']} saturation)."
        )

    return OpportunityResult(
        topic=topic,
        demand_score=round(demand, 1),
        momentum_score=round(momentum, 1),
        whitespace_score=round(whitespace, 1),
        opportunity_score=overall,
        verdict=verdict,
        reasons=reasons,
    )


if __name__ == "__main__":
    # Illustrative — same caveat as data_sources.py, needs live data to be real.
    fake_trend = {"avg_interest": 62, "latest_interest": 70, "trend_direction": "rising", "momentum_pct": 18.4}
    fake_reddit = {"post_count": 14, "total_upvotes": 890, "total_comments": 210, "engagement_score": 1310}
    fake_etsy = {"listing_count": 340, "saturation": "low"}
    result = score_idea("freelancer budgeting", fake_trend, fake_reddit, fake_etsy)
    print(result)
