"""
How-to-use page. Streamlit automatically discovers any file in a `pages/`
folder next to app.py and adds it to the sidebar navigation — no wiring
needed in app.py itself. File name convention: the leading number controls
its order in the sidebar (this page appears second, after the main app).

IMPORTANT: this file must live at pages/1_How_to_use.py in your repo, not
at the repo root — see SETUP_GUIDE.md for how to create that path via
GitHub's web UI. It's named pages_1_How_to_use.py here only because this
tool can't create a subfolder directly.
"""

import streamlit as st

st.set_page_config(page_title="How to use", page_icon=None, layout="centered")

st.write("## How to use this tool")

st.write("### 1. Pick a region and browse ideas")
st.write(
    "The main page shows PDF guide topics ranked by an **Opportunity Score** (0-100). "
    "Each score combines three real signals — not an AI guessing:"
)
st.markdown(
    "- **Demand** — how much people are actually searching for and discussing this topic\n"
    "- **Momentum** — whether interest is rising or falling right now\n"
    "- **Whitespace** — how few paid guides already exist for this exact topic"
)
st.write(
    "Ideas refresh automatically every few hours, so scores stay current without you doing anything."
)

st.write("### 2. Get the AI prompt")
st.write(
    "Open any idea card and click **Get AI prompt for this guide**. This gives you a ready-to-use "
    "prompt, already filled in with the real reasons that topic scored well — you don't have to "
    "write your own prompt from scratch."
)

st.write("### 3. Generate the content with your own AI")
st.write(
    "Copy that prompt into ChatGPT, Claude, or whichever AI tool you already use, and copy its "
    "response. This step is intentionally manual — it means using this tool never costs you "
    "anything extra in AI fees, on top of your subscription."
)

st.write("### 4. Paste it back and export")
st.write(
    "Paste the AI's response into the text box under the same idea, then click "
    "**Generate formatted PDF**. You'll get a clean, cover-paged, ready-to-sell PDF you can list "
    "on Selar, Etsy, Gumroad, or anywhere else."
)
st.info("PDF export is a paid feature. Browsing ideas and getting AI prompts is always free.")

st.write("### 5. Subscribe")
st.write(
    "Enter your email in the sidebar on the main page to check your subscription status, or click "
    "**Subscribe via Selar** there to unlock PDF export. It can take a minute or two after purchase "
    "for access to activate."
)

st.divider()
st.caption(
    "Tip: try a few different regions for the same general topic — search demand for the same "
    "guide idea can look very different in the US versus the UK or Nigeria."
)
