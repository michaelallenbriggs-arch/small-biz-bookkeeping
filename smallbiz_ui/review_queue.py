import streamlit as st
import requests

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Review Queue", layout="wide")

st.title("Receipts Needing Review")

try:
    resp = requests.get(f"{API_BASE}/review/queue", timeout=10)
    resp.raise_for_status()
    receipts = resp.json()

except Exception as e:
    st.error("Unable to load review queue")
    st.stop()

if not receipts:
    st.success("No receipts currently need review.")
    st.stop()

for r in receipts:
    with st.container(border=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.write("**Vendor:**", r.get("vendor"))
            st.write("**Date:**", r.get("date"))

        with col2:
            st.write("**Total:**", r.get("total"))
            st.write("**Category:**", r.get("category"))

        with col3:
            st.write("**Flags:**")
            for flag in r.get("flags", []):
                st.warning(flag)

        st.button(
            "Open receipt",
            key=f"open_{r.get('id')}",
            on_click=lambda rid=r.get("id"): st.session_state.update(
                {"selected_receipt": rid}
            ),
        )