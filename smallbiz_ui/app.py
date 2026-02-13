import os
import sys
import io
import re
import json
import time
import zipfile
import base64
import secrets
import hashlib
import urllib.parse
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

# Add parent directory to path for imports (MUST BE BEFORE categorizer import)
sys.path.insert(0, str(Path(__file__).parent.parent))

# Now import categorizer service
from app.services.categorizer_service import categorize_purchase

import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True))

# =============================================================================
# Configuration
# =============================================================================
API_BASE = (os.getenv("API_BASE_URL") or os.getenv("BACKEND_URL") or "http://localhost:8000").rstrip("/")
DEFAULT_LIMIT = int(os.getenv("UI_DEFAULT_LIMIT", "500"))

st.set_page_config(
    page_title="SmallBiz Bookkeeping",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# Session State Initialization
# =============================================================================
def init_session_state():
    """Initialize all session state variables"""
    defaults = {
        "access_token": None,
        "me": None,
        "business_id": None,
        "business_label": "",
        "email": "",
        "login_step": "email",  # email | code
        "last_upload": None,
        "selected_receipt_id": None,
    }
    for key, val in defaults.items():
        st.session_state.setdefault(key, val)

init_session_state()

# =============================================================================
# API Communication Layer
# =============================================================================
def _headers(*, include_business: bool = False) -> Dict[str, str]:
    """Build request headers with auth token and optional business ID"""
    h = {"Accept": "application/json"}

    tok = st.session_state.get("access_token")
    if tok:
        h["Authorization"] = f"Bearer {tok}"

    if include_business:
        bid = st.session_state.get("business_id")
        if bid is not None:
            h["X-Business-Id"] = str(int(bid))

    return h


def _handle_response(resp: requests.Response) -> Any:
    """Parse response or raise meaningful error"""
    try:
        data = resp.json()
    except Exception:
        data = {"detail": resp.text}

    if resp.status_code >= 400:
        detail = data.get("detail", str(data)) if isinstance(data, dict) else str(data)
        raise RuntimeError(f"API Error ({resp.status_code}): {detail}")

    return data


def api_get(path: str, *, params: Optional[Dict[str, Any]] = None,
            include_business: bool = False, timeout: int = 30) -> Any:
    """GET request to API"""
    url = f"{API_BASE}{path}"
    resp = requests.get(url, headers=_headers(include_business=include_business),
                       params=params, timeout=timeout)
    return _handle_response(resp)


def api_post(path: str, *, json_body: Optional[Dict[str, Any]] = None,
             data: Optional[Dict[str, Any]] = None,
             files: Optional[List] = None,
             include_business: bool = False, timeout: int = 60) -> Any:
    """POST request to API"""
    url = f"{API_BASE}{path}"
    resp = requests.post(url, headers=_headers(include_business=include_business),
                        json=json_body, data=data, files=files, timeout=timeout)
    return _handle_response(resp)


def api_patch(path: str, *, json_body: Dict[str, Any],
              include_business: bool = False, timeout: int = 30) -> Any:
    """PATCH request to API"""
    url = f"{API_BASE}{path}"
    resp = requests.patch(url, headers=_headers(include_business=include_business),
                         json=json_body, timeout=timeout)
    return _handle_response(resp)

# =============================================================================
# Authentication Flow
# =============================================================================
def render_auth_page():
    """Email-based authentication flow"""
    st.title("🔐 Sign In")
    st.markdown("### Secure email login for your business")

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        if st.session_state.get("login_step") == "email":
            st.markdown("#### Enter your email")
            email = st.text_input(
                "Email Address",
                value=st.session_state.get("email", ""),
                placeholder="you@yourbusiness.com",
                key="email_input"
            )
            st.session_state["email"] = email

            if st.button("Send Login Code", type="primary", use_container_width=True):
                if not email or "@" not in email:
                    st.error("Please enter a valid email address")
                else:
                    try:
                        api_post("/auth/request_code", json_body={"email": email})
                        st.session_state["login_step"] = "code"
                        st.success(f"✅ Code sent to {email}")
                        st.info("Check your inbox (and spam folder)")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to send code: {e}")

        else:  # code step
            st.markdown(f"#### Enter code sent to {st.session_state['email']}")
            code = st.text_input(
                "6-digit code",
                value="",
                max_chars=6,
                placeholder="123456",
                key="code_input"
            )

            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("Verify Code", type="primary", use_container_width=True):
                    if not code or len(code) != 6:
                        st.error("Please enter a 6-digit code")
                    else:
                        try:
                            result = api_post("/auth/verify_code",
                                            json_body={"email": st.session_state["email"], "code": code})

                            st.session_state["access_token"] = result.get("access_token")

                            # Fetch user info
                            me = api_get("/me")
                            st.session_state["me"] = me
                            st.session_state["business_id"] = me.get("business_id")
                            st.session_state["email"] = me.get("email")

                            st.success("✅ Login successful!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Invalid code: {e}")

            with col_b:
                if st.button("Back", use_container_width=True):
                    st.session_state["login_step"] = "email"
                    st.rerun()

        st.divider()
        st.caption(f"🔒 Secure connection to: {API_BASE}")

# =============================================================================
# Data Utilities
# =============================================================================
def safe_float(x: Any) -> Optional[float]:
    """Safely convert to float, handling currency formatting"""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip().replace("$", "").replace(",", "")
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None
    return None


def format_currency(amount: Optional[float]) -> str:
    """Format float as currency"""
    if amount is None:
        return "—"
    return f"${amount:,.2f}"


def format_confidence(conf: Optional[float]) -> str:
    """Format confidence score with color coding"""
    if conf is None:
        return "—"

    conf_val = float(conf)
    if conf_val >= 90:
        return f"🟢 {conf_val:.0f}%"
    elif conf_val >= 70:
        return f"🟡 {conf_val:.0f}%"
    else:
        return f"🔴 {conf_val:.0f}%"


def extract_normalized(row: Dict[str, Any]) -> Dict[str, Any]:
    """Extract normalized data from receipt row"""
    normalized = row.get("normalized") or {}

    return {
        "receipt_id": row.get("receipt_id"),
        "filename": row.get("filename"),
        "status": row.get("status", "active"),
        "needs_review": bool(normalized.get("needs_review", False)),
        "flags": normalized.get("flags", []),

        # Core fields
        "vendor": normalized.get("vendor"),
        "vendor_confidence": normalized.get("vendor_confidence"),

        "date": normalized.get("date"),
        "date_confidence": normalized.get("date_confidence"),

        "total": normalized.get("total"),
        "total_confidence": normalized.get("total_confidence"),

        "tax": normalized.get("tax"),

        "category": normalized.get("category"),
        "category_confidence": normalized.get("category_confidence"),

        "explanation": normalized.get("explanation"),
    }

# =============================================================================
# Upload Interface
# =============================================================================
def render_upload_section():
    """Receipt upload interface"""
    st.header("📤 Upload Receipts")

    if st.session_state.get("business_id") is None:
        st.warning("⚠️ Please set your Business ID in the sidebar first")
        return

    with st.form("upload_form", clear_on_submit=True):
        col1, col2 = st.columns([2, 1])

        with col1:
            files = st.file_uploader(
                "Select receipt images or PDFs",
                type=["png", "jpg", "jpeg", "pdf"],
                accept_multiple_files=True,
                help="Upload one or more receipts"
            )

            explanation = st.text_area(
                "Business purpose (optional)",
                placeholder="e.g., Client dinner, office supplies, equipment repair",
                help="Helps with accurate categorization"
            )

        with col2:
            business_type = st.text_input(
                "Business type (optional)",
                placeholder="Restaurant, Retail, Services",
                help="Your type of business"
            )

            business_state = st.text_input(
                "State",
                value=os.getenv("BUSINESS_STATE", "DE"),
                max_chars=2,
                help="2-letter state code for tax rules"
            )

        submitted = st.form_submit_button("Upload & Process", type="primary", use_container_width=True)

    if submitted:
            if not files:
                st.error("Please select at least one file")
            else:
                with st.spinner(f"Processing {len(files)} receipt(s)..."):
                    try:
                        files_payload = [
                            ("files", (f.name, f.getvalue(), f.type or "application/octet-stream"))
                            for f in files
                        ]

                        form_data = {
                            "business_type": business_type or "",
                            "business_state": (business_state or "DE").upper().strip(),
                            "explanation": explanation or "",
                        }

                        result = api_post(
                            "/upload",
                            data=form_data,
                            files=files_payload,
                            include_business=True,
                            timeout=180
                        )

                        st.session_state["last_upload"] = result

                        processed = result.get("processed", 0)
                        total = result.get("total", 0)

                        st.success(f"✅ Successfully processed {processed} of {total} receipts")

                        results = result.get("results", [])
                        needs_review = [r for r in results if r.get("needs_review")]

                        if needs_review:
                            st.warning(f"⚠️ {len(needs_review)} receipt(s) need review")

                        # ===== CATEGORY DISPLAY SECTION =====
                        # Display category information for each receipt
                        st.subheader("📊 Categorization Results")

                        for idx, receipt_result in enumerate(results, 1):
                            parsed = receipt_result.get("parsed", {})
                            category = parsed.get("category")
                            confidence = parsed.get("category_confidence", 0)
                            reasoning = parsed.get("category_reasoning", "")

                            with st.expander(f"Receipt {idx} - Category: {category or 'Unknown'}", expanded=(idx==1)):
                                col1, col2 = st.columns([2, 1])

                                with col1:
                                    if category:
                                        st.success(f"**Category:** {category}")
                                    else:
                                        st.warning("**Category:** Not detected")

                                    if reasoning:
                                        st.caption(f"💡 {reasoning}")

                                with col2:
                                    confidence_pct = f"{confidence * 100:.1f}%"

                                    if confidence >= 0.9:
                                        st.success(f"**Confidence:** {confidence_pct}")
                                    elif confidence >= 0.7:
                                        st.info(f"**Confidence:** {confidence_pct}")
                                    else:
                                        st.warning(f"**Confidence:** {confidence_pct}")

                                    # Visual confidence bar
                                    st.progress(confidence)
                        # ===== END CATEGORY SECTION =====

                        time.sleep(1)
                        st.rerun()

                    except Exception as e:
                        st.error(f"Upload failed: {e}")

# =============================================================================
# Receipts List & Review
# =============================================================================
def render_receipts_list():
    """Main receipts table with filtering and review"""
    st.header("📋 Receipts")

    if st.session_state.get("business_id") is None:
        st.warning("⚠️ Please set your Business ID in the sidebar first")
        return

    # Filters
    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

    with col1:
        view_mode = st.selectbox(
            "View",
            ["All Receipts", "Needs Review", "Clean Only"],
            help="Filter receipts by review status"
        )

    with col2:
        status_filter = st.selectbox(
            "Status",
            ["active", "archived", "all"],
            help="Receipt status"
        )

    with col3:
        limit = st.number_input(
            "Limit",
            min_value=10,
            max_value=1000,
            value=DEFAULT_LIMIT,
            step=50
        )

    with col4:
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()

    # Determine filter
    needs_review_filter = None
    if view_mode == "Needs Review":
        needs_review_filter = True
    elif view_mode == "Clean Only":
        needs_review_filter = False

    # Fetch data
    try:
        params = {"limit": int(limit), "status": status_filter}
        if needs_review_filter is not None:
            params["needs_review"] = str(needs_review_filter).lower()

        receipts = api_get("/receipts", params=params, include_business=True)

        if not receipts:
            st.info("No receipts found. Upload some receipts to get started!")
            return

        # Process for display
        display_data = []
        for r in receipts:
            norm = extract_normalized(r)

            display_data.append({
                "ID": norm["receipt_id"],
                "Vendor": norm["vendor"] or "—",
                "Date": norm["date"] or "—",
                "Total": format_currency(norm["total"]),
                "Tax": format_currency(norm["tax"]),
                "Category": norm["category"] or "—",
                "Status": "⚠️ Review" if norm["needs_review"] else "✅ Clean",
                "Confidence": format_confidence(norm["total_confidence"]),
                "_raw": r  # Keep raw data for detail view
            })

        df = pd.DataFrame(display_data)

        # Sort: problems first
        df = df.sort_values(
            by=["Status", "Date"],
            ascending=[False, False]
        )

        st.dataframe(
            df.drop(columns=["_raw"]),
            use_container_width=True,
            hide_index=True,
            column_config={
                "ID": st.column_config.NumberColumn("ID", width="small"),
                "Total": st.column_config.TextColumn("Total", width="small"),
                "Tax": st.column_config.TextColumn("Tax", width="small"),
                "Confidence": st.column_config.TextColumn("Confidence", width="medium"),
            }
        )

        st.divider()

        # Detail view & editing
        render_receipt_detail(df)

        st.divider()

        # Export section
        render_export_section(df)

    except Exception as e:
        st.error(f"Failed to load receipts: {e}")


def render_receipt_detail(df: pd.DataFrame):
    """Individual receipt review and editing"""
    st.subheader("🔍 Review & Edit")

    if df.empty:
        return

    receipt_ids = df["ID"].tolist()

    selected_id = st.selectbox(
        "Select receipt to review",
        receipt_ids,
        format_func=lambda x: f"Receipt #{x}",
        key="detail_selector"
    )

    if not selected_id:
        return

    try:
        # Fetch full details
        detail = api_get(f"/receipts/{int(selected_id)}", include_business=True)
        normalized = detail.get("normalized", {})
        parsed = detail.get("parsed", {})
        flags = detail.get("flags", [])
        needs_review = detail.get("needs_review", False)

        # Display current status
        col_status, col_conf = st.columns([1, 1])

        with col_status:
            st.markdown("**Status**")
            if needs_review:
                st.error("⚠️ Needs Review")
            else:
                st.success("✅ Clean")

            if flags:
                st.markdown("**Flags:**")
                for flag in flags:
                    st.caption(f"• {flag}")

        with col_conf:
            st.markdown("**Confidence Scores**")
            st.write(f"Vendor: {format_confidence(normalized.get('vendor_confidence'))}")
            st.write(f"Date: {format_confidence(normalized.get('date_confidence'))}")
            st.write(f"Total: {format_confidence(normalized.get('total_confidence'))}")
            st.write(f"Category: {format_confidence(normalized.get('category_confidence'))}")

        st.divider()

        # Editable fields
        with st.form(f"edit_form_{selected_id}"):
            st.markdown("**Edit Fields**")

            col1, col2 = st.columns(2)

            with col1:
                vendor = st.text_input(
                    "Vendor",
                    value=str(normalized.get("vendor") or ""),
                    help="Business name"
                )

                date = st.text_input(
                    "Date",
                    value=str(normalized.get("date") or ""),
                    help="YYYY-MM-DD format"
                )

                total = st.text_input(
                    "Total",
                    value=str(normalized.get("total") or ""),
                    help="Total amount"
                )

            with col2:
                tax = st.text_input(
                    "Tax",
                    value=str(normalized.get("tax") or ""),
                    help="Sales tax amount"
                )

                category = st.text_input(
                    "Category",
                    value=str(normalized.get("category") or ""),
                    help="Expense category"
                )

            explanation = st.text_area(
                "Business Purpose",
                value=str(normalized.get("explanation") or parsed.get("explanation") or ""),
                help="Why this expense is business-related"
            )

            submitted = st.form_submit_button("💾 Save Changes", type="primary", use_container_width=True)

            if submitted:
                try:
                    patch_data = {
                        "vendor": vendor.strip() or None,
                        "date": date.strip() or None,
                        "total": safe_float(total),
                        "tax": safe_float(tax),
                        "category": category.strip() or None,
                        "explanation": explanation.strip() or None,
                    }

                    updated = api_patch(
                        f"/receipts/{int(selected_id)}/review",
                        json_body=patch_data,
                        include_business=True
                    )

                    st.success("✅ Receipt updated successfully!")
                    st.info("Flags and review status have been recomputed automatically.")
                    time.sleep(1)
                    st.rerun()

                except Exception as e:
                    st.error(f"Update failed: {e}")

        # Debug view
        with st.expander("🔧 Raw Data (Debug)", expanded=False):
            st.json(detail)

    except Exception as e:
        st.error(f"Failed to load receipt details: {e}")


def render_export_section(df: pd.DataFrame):
    """Export and archive functionality"""
    st.subheader("📦 Export & Archive")

    col1, col2 = st.columns(2)

    with col1:
        # CSV export
        if not df.empty:
            csv_data = df.drop(columns=["_raw"], errors="ignore").to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Download CSV",
                data=csv_data,
                file_name=f"receipts_export_{int(time.time())}.csv",
                mime="text/csv",
                use_container_width=True
            )

    with col2:
        # Archive functionality
        if st.button("🗄️ Archive & Export", use_container_width=True, help="Mark receipts as exported and archive them"):
            st.info("Select receipts to archive in the table above, then use this button.")
            # Note: Full archive implementation would require selection mechanism

# =============================================================================
# Sidebar
# =============================================================================
def render_sidebar():
    """Application sidebar with user info and settings"""
    with st.sidebar:
        st.title("⚙️ Settings")

        me = st.session_state.get("me", {})

        st.markdown("### User")
        st.write(f"**Email:** {me.get('email', 'Not logged in')}")

        st.divider()

        st.markdown("### Business")

        # Business ID (from JWT)
        current_bid = st.session_state.get("business_id")
        if current_bid:
            st.write(f"**ID:** {current_bid}")
        else:
            st.warning("No business ID set")

        # Business label (UI-only)
        business_label = st.text_input(
            "Business Name (optional)",
            value=st.session_state.get("business_label", ""),
            placeholder="My Business LLC",
            help="Display name for your business"
        )
        st.session_state["business_label"] = business_label

        st.divider()

        # Logout
        if st.button("🚪 Logout", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            init_session_state()
            st.rerun()

        st.divider()

        st.caption(f"🔗 API: {API_BASE}")
        st.caption("Version 1.0 • Production")

# =============================================================================
# Main Application
# =============================================================================
def main():
    """Main application router"""

    # Check authentication
    if not st.session_state.get("access_token"):
        render_auth_page()
        return

    # Render sidebar
    render_sidebar()

    # Main content tabs
    tab1, tab2 = st.tabs(["📤 Upload", "📋 Receipts"])

    with tab1:
        render_upload_section()

    with tab2:
        render_receipts_list()


if __name__ == "__main__":
    main()