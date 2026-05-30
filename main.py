from __future__ import annotations
import sys
import os
import sqlite3

import streamlit as st
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.cache import DB_PATH
from app.core.config import SenderInfo, ReceiverInfo, PitchContext
from app.agents.agent import run_email_drafter
from app.services.notion_crm import save_to_notion
from app.models.company_selector import select_companies


# Setup Streamlit Page
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Smart Outreach Emailer",
    page_icon="",
    layout="wide",
)

st.title("Smart Outreach Emailer")
st.markdown("Generate leads . Analyzes Relevance . Drafts Email")

# Env check
if not os.getenv("GROQ_API_KEY"):
    st.error("GROQ_API_KEY not set. Add it to your .env file.")
    st.stop()



# Sidebar / Sender Info
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("📤 Sender Info")
    sender_name = st.text_input("Name", value="Pratyush")
    sender_role = st.text_input("Role", value="Product Manager")
    sender_company = st.text_input("Company Name", value="PRG")
    sender_website = st.text_input("Website", value="https://pratyushrdesign.framer.website/")
    sender_desc = st.text_area("Description", value="Providing Branding, UI/UX, and Web Design Solutions to Elevate Your Digital Experience.")
    sender_service = st.text_input("Service Offered", value="Branding, UI/UX, and Web Design")
    sender_usp = st.text_input("USP", value="Perfection, uniqueness, delivering the best ")

    sender = SenderInfo(
        name=sender_name,
        role=sender_role,
        company_name=sender_company,
        company_website=sender_website or None,
        company_desc=sender_desc or None,
        service_offered=sender_service,
        usp=sender_usp or None,
    )
# Main Form: Pitch Context & Receiver Selection
# ─────────────────────────────────────────────────────────────────────────────

# Fetch cached companies
def get_cached_companies():
    if not os.path.exists(DB_PATH):
        return []
    try:
        con = sqlite3.connect(DB_PATH)
        rows = con.execute(
            "SELECT company_key, company_name, receiver FROM receiver_cache ORDER BY fetched_at DESC"
        ).fetchall()
        con.close()
        return rows
    except Exception as e:
        st.error(f"Database error: {e}")
        return []

rows = get_cached_companies()

if not rows:
    st.warning("No cached companies found. Run Researcher.py first to fetch companies.")
    st.stop()

# Parse and get ML predictions for all companies
parsed_receivers = [ReceiverInfo.model_validate_json(row[2]) for row in rows]
predictions = select_companies(parsed_receivers)

companies_data = []
ml_selected_count = 0
for i, (key, name, receiver_json) in enumerate(rows):
    receiver = parsed_receivers[i]
    pred = predictions[i][1]
    if pred == 1:
        ml_selected_count += 1
    companies_data.append({
        "index": i,
        "key": key,
        "name": name,
        "receiver": receiver,
        "prediction": pred
    })

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📥 Select the Target Company")
    
    # Display ML Summary metrics with nice UI styling
    st.markdown(f"**ML Classification Summary:** 🎯 **{ml_selected_count}** of **{len(companies_data)}** recommended for outreach.")
    
    # Horizontal filter options
    filter_option = st.radio(
        "Filter list by ML relevance prediction:",
        options=["All Startups", "ML Selected Only (Highly Relevant)", "ML Excluded Only (Low Relevance)"],
        horizontal=True
    )
    
    selected_receivers = []
    
    with st.container(height=500):
        for comp in companies_data:
            pred = comp["prediction"]
            
            # Apply filter selection
            if filter_option == "ML Selected Only (Highly Relevant)" and pred != 1:
                continue
            if filter_option == "ML Excluded Only (Low Relevance)" and pred != 0:
                continue
                
            receiver = comp["receiver"]
            industry = receiver.industry or "N/A"
            website = receiver.company_website or "N/A"
            trigger_point = receiver.trigger_point or "N/A"
            
            # Show a beautiful badge indicating ML status
            badge = "🟢 **ML SELECTED (High Fit)**" if pred == 1 else "❌ **ML EXCLUDED (Low Fit)**"
            label = f"**{comp['name']}** — {badge}  \n*Industry:* {industry} | *Website:* {website} | *Trigger Point:* {trigger_point}"
            
            # Default checkbox state: True if ML prediction is 1, False if 0
            default_val = (pred == 1)
            
            if st.checkbox(label, key=f"company_{comp['index']}", value=default_val):
                selected_receivers.append(receiver)
    
    if selected_receivers:
        st.info(f"Selected **{len(selected_receivers)}** companies.")

with col2:
    st.subheader(" Pitch Context")
    goal = st.selectbox("Email goal", ["demo", "discovery_call", "free_trial", "partnership", "custom"])
    if goal == "custom":
        goal = st.text_input("Describe your custom goal")
        
    tone = st.selectbox("Tone", ["professional", "friendly", "bold", "concise"])
    length = st.selectbox("Email length", ["short", "medium", "long"], index=1)
    
    pain_points = st.text_area("Known pain points (optional)")
    subject_hint = st.text_input("Subject line hint (optional)")
    custom_notes = st.text_input("Extra instructions (optional)")

    ctx = PitchContext(
        goal=goal,
        tone=tone,
        email_length=length,
        pain_points=pain_points or None,
        subject_hint=subject_hint or None,
        custom_notes=custom_notes or None,
    )


# Execution
# ─────────────────────────────────────────────────────────────────────────────
st.divider()

if st.button(" Generate Emails", type="primary"):
    if not selected_receivers:
        st.error("Please select at least one company to generate an email for.")
    else:
        # Enforce that only leads selected by ML (prediction == 1) are processed by agent.py
        valid_receivers = []
        for r in selected_receivers:
            # Find the prediction for this receiver
            pred = next((c["prediction"] for c in companies_data if c["receiver"].company_name == r.company_name), 0)
            if pred == 1:
                valid_receivers.append(r)
            else:
                st.warning(f"⚠️ Skipping outreach generation for **{r.company_name}** because the ML model classified it as Excluded.")
        
        if not valid_receivers:
            st.error("No valid ML-selected companies are selected for generation.")
        else:
            for idx, receiver in enumerate(valid_receivers):
                st.subheader(f"Email {idx+1}: {receiver.company_name}")
            
            with st.spinner(f"Drafting email for {receiver.company_name}..."):
                try:
                    result = run_email_drafter(sender, receiver, ctx)
                    
                    # Display Results
                    subject = result.get('subject_line', 'No Subject Generated')
                    body = result.get('final_email', '')
                    
                    # Clean up body prefixes if needed
                    for artifact in ["SUBJECT:", "---"]:
                        if body.startswith(artifact):
                            body = body[len(artifact):].strip()
                            
                    with st.expander(f"Subject: {subject}", expanded=True):
                        st.write(body)
                        
                        cols = st.columns(2)
                        with cols[0]:
                            review_passed = result.get('review_passed', False)
                            st.caption(f"**Review Passed:** {'Yes' if review_passed else 'Forced Finalize'}")
                            st.caption(f"**Iterations:** {result.get('iterations', 0)}")
                            
                        
                    if 'analysis' in result and result['analysis']:
                        
                        with st.expander("Show Analysis"):
                            st.write(result['analysis'])
                                    
                    # Save to Notion
                    with st.spinner("Saving to Notion..."):
                        save_to_notion(receiver)
                    st.success(f"Saved to Notion for {receiver.company_name}!")
                    
                except Exception as e:
                    st.error(f"Error generating email for {receiver.company_name}: {e}")
