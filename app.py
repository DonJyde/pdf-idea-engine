"""
Streamlit app - the whole user-facing product.

Reads ranked ideas from the `ideas` table (populated by refresh_job.py on a
schedule - this app never scrapes live), filtered by the region the user
picks. Free tier: unlimited browsing of ideas + Opportunity Scores + the
copy-paste AI prompt. Paid tier (gated by a Supabase `subscribers` row,
populated by a Zapier automation on Selar purchase): one-click formatted
PDF export.

A separate "How to use" page lives in pages/1_How_to_use.py - Streamlit
automatically adds it to the sidebar navigation, no wiring needed here.

Run locally:
    streamlit run app.py

Environment variables required (.env locally, "Environment" secrets on Render):
    SUPABASE_URL
    SUPABASE_ANON_KEY   - the public anon/publishable key (read-only by RLS
                           policy, see SETUP_GUIDE.md - never use the secret key here)
    SELAR_CHECKOUT_URL  - link to your Selar subscription product page
"""

import os

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client

from data_sources import REGIONS
from pdf_builder import build_pdf, build_ai_prompt

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
SELAR_CHECKOUT_URL = os.environ.get("SELAR_CHECKOUT_URL", "https://selar.com/")

st.set_page_config(page_title="PDF Guide Idea Engine", page_icon=None, layout="centered")


@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def is_active_subscriber(email):
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


def load_ideas(geo):
    supabase = get_client()
    resp = (
        supabase.table("ideas")
        .select("*")
        .eq("geo", geo)
        .order("opportunity_score", desc=True)
        .execute()
    )
    return resp.data


def verdict_color(verdict):
    if verdict.startswith("Strong"):
        return "green"
    if verdict.startswith("Worth"):
        return "orange"
    return "red"


with st.sidebar:
    st.write("### Your account")
    email = st.text_input("Email (used at Selar checkout)")
    subscribed = is_active_subscriber(email) if email else False
    if email and subscribed:
        st.success("Active subscriber - full PDF export unlocked.")
    elif email:
        st.info("Free tier - ideas and AI prompts are unlocked. Subscribe for one-click PDF export.")
        st.link_button("Subscribe via Selar", SELAR_CHECKOUT_URL)
    else:
        st.caption("Enter your email to check subscription status. Browsing ideas doesn't require it.")

    st.divider()
    st.caption("New here? See the How to use page in the sidebar navigation above.")

st.write("## Guide ideas ranked by real demand")
st.caption("Refreshed on a schedule from Google Trends, Reddit, and Etsy - not an AI guess.")

AVAILABLE_REGION_CODES = ["US", "GB", "NG"]
available_regions = []
for r in REGIONS:
    if r["code"] in AVAILABLE_REGION_CODES:
        available_regions.append(r)

region_labels = []
for r in available_regions:
    region_labels.append(r["label"])

selected_label = st.selectbox("Region", region_labels, index=0)

selected_geo = None
for r in available_regions:
    if r["label"] == selected_label:
        selected_geo = r["code"]
        break

try:
    ideas = load_ideas(selected_geo)
except Exception as e:
    ideas = []
    st.error("Couldn't reach the ideas database. Error: " + str(e))

if not ideas:
    st.warning(
        "No cached ideas yet for " + selected_label + ". Run refresh_job.py "
        "(see SETUP_GUIDE.md) with this region added to ACTIVE_REGIONS first."
    )

for idea in ideas:
    with st.container(border=True):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.write("**" + idea["topic"] + "**")
            reasons = idea.get("reasons") or []
            for r in reasons:
                st.caption("- " + r)
        with col2:
            st.metric("Score", "{:.0f}".format(idea["opportunity_score"]))
            st.caption(":" + verdict_color(idea["verdict"]) + "[" + idea["verdict"] + "]")

        with st.expander("Get AI prompt for this guide"):
            prompt_text = build_ai_prompt(idea["topic"], reasons)
            st.code(prompt_text, language=None)
            st.caption("Copy this into your own ChatGPT/Claude, then paste the result below.")

            pasted = st.text_area(
                "Paste the AI's guide content here",
                key="paste_" + str(idea["id"]),
                height=200,
            )

            if subscribed:
                if st.button("Generate formatted PDF", key="gen_" + str(idea["id"])):
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
                            file_name=idea["topic"].replace(" ", "_") + ".pdf",
                            mime="application/pdf",
                            key="dl_" + str(idea["id"]),
                        )
            else:
                st.info("Formatted PDF export is a paid feature. Subscribe via Selar to unlock it.")
