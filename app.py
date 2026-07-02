"""
Streamlit app — the whole user-facing product.

Reads ranked ideas from the `ideas` table (populated by refresh_job.py on a
schedule — this app never scrapes live). Free tier: unlimited browsing of
ideas + Opportunity Scores + the copy-paste AI prompt. Paid tier (gated by
a Supabase `subscribers` row, populated by a Zapier automation on Selar
purchase): one-click formatted PDF export.

Run locally:
    streamlit run app.py

Environment variables required (.env locally, "Environment" secrets on Render):
    SUPABASE_URL
    SUPABASE_ANON_KEY   — the public anon key (read-only by RLS policy, see
                           SETUP_GUIDE.md — never use the service key here)
    SELAR_CHECKOUT_URL  — link to your Selar subscription product page
"""

import os

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

from pdf_builder import build_pdf, build_ai_prompt

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SELAR_CHECKOUT_URL = os.environ.get("SELAR_CHECKOUT_URL", "https://selar.com/")

st.set_page_config(page_title="PDF Guide Idea Engine", page_icon=None, layout="centered")


@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def is_active_subscriber(email: str) -> bool:
    """Checks the `subscribers` table, which Zapier keeps in sync with Selar
    purchase/cancellation events. Fails safe (treats as free tier) if the
    lookup errors, rather than crashing the whole app for a paying user."""
    if not email:
        return False
    try:
        supabase = get_client()
        resp = (
            supabase.table("subscribers")
            .select("status")
            .eq("email", email.strip().lower())
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        return len(resp.data) > 0
    except Exception:
        return False


def load_ideas():
    supabase = get_client()
    resp = supabase.table("ideas").select("*").order("opportunity_score", desc=True).execute()
    return resp.data


def verdict_color(verdict: str) -> str:
    if verdict.startswith("Strong"):
        return "green"
    if verdict.startswith("Worth"):
        return "orange"
    return "red"


# ---------------- Sidebar: access ----------------
with st.sidebar:
    st.write("### Your account")
    email = st.text_input("Email (used at Selar checkout)")
    subscribed = is_active_subscriber(email) if email else False
    if email and subscribed:
        st.success("Active subscriber — full PDF export unlocked.")
    elif email:
        st.info("Free tier — ideas and AI prompts are unlocked. Subscribe for one-click PDF export.")
        st.link_button("Subscribe via Selar", SELAR_CHECKOUT_URL)
    else:
        st.caption("Enter your email to check subscription status. Browsing ideas doesn't require it.")

# ---------------- Main: idea list ----------------
st.write("## Guide ideas ranked by real demand")
st.caption("Refreshed on a schedule from Google Trends, Reddit, and Etsy — not an AI guess.")

try:
    ideas = load_ideas()
except Exception as e:
    ideas = []
    st.error(
        "Couldn't reach the ideas database. If you're running this locally without Supabase "
        f"configured yet, that's expected. ({e})"
    )

if not ideas:
    st.warning(
        "No cached ideas yet. Run `refresh_job.py` (see SETUP_GUIDE.md) to populate the "
        "`ideas` table before the dashboard has anything to show."
    )

for idea in ideas:
    with st.container(border=True):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write(f"**{idea['topic']}**")
            reasons = idea.get("reasons") or []
            for r in reasons:
                st.caption(f"- {r}")
        with col2:
            st.metric("Score", f"{idea['opportunity_score']:.0f}")
            st.caption(f":{verdict_color(idea['verdict'])}[{idea['verdict']}]")

        with st.expander("Get AI prompt for this guide"):
            prompt_text = build_ai_prompt(idea["topic"], reasons)
            st.code(prompt_text, language=None)
            st.caption("Copy this into your own ChatGPT/Claude, then paste the result below.")

            pasted = st.text_area(
                "Paste the AI's guide content here",
                key=f"paste_{idea['id']}",
                height=200,
            )

            if subscribed:
                if st.button("Generate formatted PDF", key=f"gen_{idea['id']}"):
                    if not pasted.strip():
                        st.warning("Paste the AI-generated content above first.")
                    else:
                        pdf_bytes = build_pdf(
                            topic=idea["topic"],
                            subtitle="A practical guide",
                            raw_text=pasted,
                        )
                        st.download_button(
                            "Download PDF",
                            data=pdf_bytes,
                            file_name=f"{idea['topic'].replace(' ', '_')}.pdf",
                            mime="application/pdf",
                            key=f"dl_{idea['id']}",
                        )
            else:
                st.info("Formatted PDF export is a paid feature. Subscribe via Selar to unlock it.")
