"""
app.py
------
Streamlit UI for AI-Powered Expense Automation.
Run with: streamlit run app.py
"""

import os
import sys
import tempfile
import streamlit as st
import pandas as pd
from PIL import Image
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add src to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.ocr_engine import extract_text
from src.text_cleaner import parse_receipt
from src.categorizer import categorize_expense
from src.reconciler import load_bank_statement, reconcile
from src.sheets_exporter import export_receipt, export_to_csv
from src.ai_formatter import format_receipt_output


# ─────────────────────────────────────────────
# PAGE CONFIGURATION
# ─────────────────────────────────────────────

st.set_page_config(
    page_title="AI Expense Automation",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ─────────────────────────────────────────────
# CUSTOM CSS
# ─────────────────────────────────────────────

st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1f3c88;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: #f8f9ff;
        border: 1px solid #e0e4ff;
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
    }
    .status-matched {
        background: #d4edda;
        color: #155724;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .status-review {
        background: #fff3cd;
        color: #856404;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .status-unmatched {
        background: #f8d7da;
        color: #721c24;
        padding: 4px 12px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .pipeline-step {
        background: white;
        border-left: 4px solid #1f3c88;
        padding: 0.8rem 1rem;
        margin: 0.5rem 0;
        border-radius: 0 8px 8px 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.image("https://img.icons8.com/color/96/invoice.png", width=80)
        st.markdown("## ⚙️ Configuration")
        st.markdown("---")

        # Bank statement upload
        st.markdown("### 🏦 Bank Statement")
        bank_file = st.file_uploader(
            "Upload CSV bank statement",
            type=["csv"],
            help="Upload your bank statement in CSV format"
        )

        bank_df = None
        if bank_file:
            try:
                # Save temp file
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".csv"
                ) as tmp:
                    tmp.write(bank_file.read())
                    tmp_path = tmp.name

                bank_df = load_bank_statement(tmp_path)
                st.success(f"✅ {len(bank_df)} transactions loaded")
            except Exception as e:
                st.error(f"❌ Error: {e}")
        else:
            # Use default sample if available
            default_bank = "data/bank_statements/sample_bank.csv"
            if os.path.exists(default_bank):
                try:
                    bank_df = load_bank_statement(default_bank)
                    st.info(f"📂 Using sample bank statement ({len(bank_df)} transactions)")
                except Exception:
                    pass

        st.markdown("---")

        # Google Sheets config
        st.markdown("### 📊 Google Sheets")
        sheets_enabled = os.path.exists("credentials.json") and \
                         bool(os.getenv("GOOGLE_SHEETS_ID"))

        if sheets_enabled:
            st.success("✅ Google Sheets connected")
        else:
            st.warning("⚠️ Google Sheets not configured")
            st.caption("Add credentials.json and GOOGLE_SHEETS_ID to .env")

        st.markdown("---")

        # About section
        st.markdown("### ℹ️ About")
        st.caption(
            "AI-Powered Expense Automation PoC\n\n"
            "Pipeline: OCR → Clean → Categorize → Reconcile → Export"
        )

        st.markdown("---")
        st.caption("Built with Python + Streamlit")

    return bank_df, sheets_enabled


# ─────────────────────────────────────────────
# PIPELINE RUNNER
# ─────────────────────────────────────────────

def run_pipeline(file_path: str, bank_df, sheets_enabled: bool) -> dict:
    """Run the full processing pipeline with live progress updates."""

    progress = st.progress(0)
    status   = st.empty()

    # ── Stage 1: OCR ─────────────────────────────────────────────
    status.markdown(
        '<div class="pipeline-step">📸 Stage 1/4 — Extracting text with OCR...</div>',
        unsafe_allow_html=True
    )
    progress.progress(10)

    ocr_result = extract_text(file_path)

    if not ocr_result.get("text"):
        st.error("❌ OCR failed — could not extract text from image.")
        return {}

    progress.progress(25)
    st.toast(f"✅ OCR done — {len(ocr_result['text'])} characters extracted", icon="📸")

    # ── Stage 2: Clean & Parse ────────────────────────────────────
    # Stage 2: Clean & Parse
    status.markdown(
        '<div class="pipeline-step">🧹 Stage 2/4 — Cleaning with AI (Gemini)...</div>',
        unsafe_allow_html=True
    )
    progress.progress(35)

    parsed = parse_receipt(ocr_result)

    # Show which method was used
    method = parsed.get("extraction_method", "rules")
    if "llm" in method:
        st.toast("🤖 Gemini AI extracted the data!", icon="✨")
    else:
        st.toast("📐 Rule-based extraction used", icon="📋")

    progress.progress(50)
    # ── Stage 3: Categorize ───────────────────────────────────────
    status.markdown(
        '<div class="pipeline-step">🏷️ Stage 3/4 — AI categorizing expense...</div>',
        unsafe_allow_html=True
    )
    progress.progress(60)

    categorized = categorize_expense(parsed)
    categorized = format_receipt_output(categorized)
    progress.progress(70)
    st.toast(f"✅ Categorized as: {categorized['category']}", icon="🏷️")

    # ── Stage 4: Reconcile ────────────────────────────────────────
    status.markdown(
        '<div class="pipeline-step">🏦 Stage 4/4 — Matching with bank statement...</div>',
        unsafe_allow_html=True
    )
    progress.progress(80)

    if bank_df is not None:
        final = reconcile(categorized, bank_df)
    else:
        categorized["reconciliation_status"]    = "not_run"
        categorized["matched_bank_description"] = ""
        categorized["matched_transaction_id"]   = ""
        categorized["match_confidence"]         = 0
        final = categorized

    progress.progress(90)

    # ── Export ────────────────────────────────────────────────────
    status.markdown(
        '<div class="pipeline-step">📤 Exporting results...</div>',
        unsafe_allow_html=True
    )

    if sheets_enabled:
        export_receipt(final)
        st.toast("✅ Saved to Google Sheets", icon="📊")
    else:
        export_to_csv([final])
        st.toast("✅ Saved to local CSV", icon="💾")

    progress.progress(100)
    status.empty()

    return final


# ─────────────────────────────────────────────
# RESULTS DISPLAY
# ─────────────────────────────────────────────

def display_results(result: dict, uploaded_image=None):
    """Display the processed receipt results in a clean layout."""

    st.markdown("---")
    st.markdown("## ✅ Processing Complete")

    # ── Top metrics row ───────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("🏪 Vendor", result.get("vendor_name", "Unknown"))
    with col2:
        amount = result.get("total_amount", 0)
        st.metric("💰 Amount", f"Rs {amount:,.2f}")
    with col3:
        st.metric("🏷️ Category", result.get("category", "Unknown"))
    with col4:
        recon = result.get("reconciliation_status", "not_run")
        icons = {
            "matched"       : "✅ Matched",
            "possible_match": "⚠️ Review",
            "unmatched"     : "❌ Unmatched",
            "not_run"       : "⏳ Pending"
        }
        st.metric("🏦 Bank Match", icons.get(recon, recon))

    # ── AI Engine Badge ───────────────────────────────────────────
    st.markdown("---")
    extraction_method = result.get("extraction_method", "")
    category_method   = result.get("category_method", "")

    badge_col1, badge_col2, badge_col3 = st.columns(3)

    with badge_col1:
        if "llm_gemini" in extraction_method:
            st.success("🤖 **Extracted by:** Gemini AI (LangChain)")
        else:
            st.info("📐 **Extracted by:** Rule-based (Regex)")

    with badge_col2:
        ocr_engine = result.get("ocr_engine", "unknown")
        engine_display = {
            "tesseract"              : "⚡ Tesseract OCR",
            "easyocr"                : "🔍 EasyOCR",
            "tesseract (low confidence)": "⚠️ Tesseract (low conf)"
        }
        st.info(f"📸 **OCR Engine:** {engine_display.get(ocr_engine, ocr_engine)}")

    with badge_col3:
        confidence = result.get("confidence", "")
        conf_display = {
            "high"  : "🟢 High Confidence",
            "medium": "🟡 Medium Confidence",
            "low"   : "🔴 Low Confidence"
        }
        if confidence in conf_display:
            st.info(f"📊 **LLM Confidence:** {conf_display[confidence]}")
        else:
            cat_conf = result.get("category_confidence", 0)
            st.info(f"📊 **Category Confidence:** {cat_conf:.0%}")

    st.markdown("---")
    # ── Two column layout ─────────────────────────────────────────
    left_col, right_col = st.columns([1, 1])

    with left_col:
        st.markdown("### 📋 Extracted Details")

        details = {
            "Vendor Name"    : result.get("vendor_name", "—"),
            "Date"           : result.get("date", "—"),
            "Total Amount"   : f"Rs {result.get('total_amount', 0):,.2f}",
            "Category"       : result.get("category", "—"),
            "Project"        : result.get("project_name", "—"),
            "OCR Engine"     : result.get("ocr_engine", "—"),
            "Category Method": result.get("category_method", "—"),
        }

        for label, value in details.items():
            col_a, col_b = st.columns([2, 3])
            col_a.markdown(f"**{label}**")
            col_b.markdown(str(value))

        st.markdown("### 🏦 Reconciliation")

        recon_status = result.get("reconciliation_status", "not_run")

        if recon_status == "matched":
            st.success(f"✅ Matched with bank entry")
        elif recon_status == "possible_match":
            st.warning(f"⚠️ Possible match — needs review")
        elif recon_status == "unmatched":
            st.error(f"❌ No matching bank entry found")
        else:
            st.info("⏳ Reconciliation not run")

        if result.get("matched_bank_description"):
            recon_details = {
                "Bank Entry"     : result.get("matched_bank_description", "—"),
                "Transaction ID" : result.get("matched_transaction_id", "—"),
                "Confidence"     : f"{result.get('match_confidence', 0):.0%}",
            }
            for label, value in recon_details.items():
                col_a, col_b = st.columns([2, 3])
                col_a.markdown(f"**{label}**")
                col_b.markdown(str(value))

    with right_col:
        # Show uploaded image
        if uploaded_image:
            st.markdown("### 🧾 Receipt Image")
            st.image(uploaded_image, use_column_width=True)

        # Show raw OCR text
        with st.expander("📄 View Raw OCR Text", expanded=False):
            st.text(result.get("raw_text", "No text extracted"))

    # ── Export confirmation ───────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📤 Export")

    exp_col1, exp_col2 = st.columns(2)
    with exp_col1:
        if os.path.exists("data/outputs/expenses.csv"):
            with open("data/outputs/expenses.csv", "rb") as f:
                st.download_button(
                    label="⬇️ Download CSV",
                    data=f,
                    file_name="expenses.csv",
                    mime="text/csv"
                )
    with exp_col2:
        sheets_id = os.getenv("GOOGLE_SHEETS_ID")
        if sheets_id:
            sheet_url = f"https://docs.google.com/spreadsheets/d/{sheets_id}"
            st.link_button("📊 Open Google Sheet", sheet_url)


# ─────────────────────────────────────────────
# BATCH PROCESSING TAB
# ─────────────────────────────────────────────

def render_batch_tab(bank_df, sheets_enabled):
    """Render the batch processing interface."""

    st.markdown("### 📦 Batch Process Multiple Receipts")
    st.caption("Upload multiple receipt images at once")

    uploaded_files = st.file_uploader(
        "Upload receipts",
        type=["jpg", "jpeg", "png", "pdf"],
        accept_multiple_files=True,
        key="batch_uploader"
    )

    if not uploaded_files:
        st.info("👆 Upload multiple receipts above to process them all at once.")
        return

    st.info(f"📋 {len(uploaded_files)} file(s) ready to process")

    if st.button("🚀 Process All Receipts", type="primary"):
        results = []

        for i, file in enumerate(uploaded_files):
            st.markdown(f"**Processing {i+1}/{len(uploaded_files)}: {file.name}**")

            with tempfile.NamedTemporaryFile(
                delete=False,
                suffix=os.path.splitext(file.name)[1]
            ) as tmp:
                tmp.write(file.read())
                tmp_path = tmp.name

            result = run_pipeline(tmp_path, bank_df, sheets_enabled)
            if result:
                result["file"] = file.name
                results.append(result)

            os.unlink(tmp_path)

        if results:
            st.markdown("### 📊 Batch Results")

            # Summary table
            table_data = []
            for r in results:
                recon = r.get("reconciliation_status", "—")
                icons = {
                    "matched": "✅", "possible_match": "⚠️",
                    "unmatched": "❌", "not_run": "⏳"
                }
                table_data.append({
                    "File"      : r.get("file", "—"),
                    "Vendor"    : r.get("vendor_name", "—"),
                    "Date"      : r.get("date", "—"),
                    "Amount"    : f"Rs {r.get('total_amount', 0):,.2f}",
                    "Category"  : r.get("category", "—"),
                    "Status"    : f"{icons.get(recon, '?')} {recon}",
                })

            st.dataframe(
                pd.DataFrame(table_data),
                use_container_width=True,
                hide_index=True
            )

            # Export batch results
            export_to_csv(results)
            st.success(f"✅ {len(results)} receipts processed and saved!")


# ─────────────────────────────────────────────
# MAIN APP
# ─────────────────────────────────────────────

def main():
    # Header
    st.markdown(
        '<p class="main-header">💼 AI Expense Automation</p>',
        unsafe_allow_html=True
    )
    st.markdown(
        '<p class="sub-header">Upload receipts → Extract → Categorize → '
        'Reconcile → Export to Google Sheets</p>',
        unsafe_allow_html=True
    )

    # Sidebar
    bank_df, sheets_enabled = render_sidebar()

    # Main tabs
    tab1, tab2 = st.tabs([
        "📸 Single Receipt",
        "📦 Batch Process",
        # "📊 View History"
    ])

    # ── Tab 1: Single Receipt ─────────────────────────────────────
    with tab1:
        st.markdown("### 📤 Upload Receipt")

        uploaded_file = st.file_uploader(
            "Choose a receipt image or PDF",
            type=["jpg", "jpeg", "png", "pdf"],
            help="Supported: JPG, PNG, PDF"
        )

        if uploaded_file:
            # Show preview
            col1, col2 = st.columns([1, 2])
            with col1:
                st.markdown("**Preview:**")
                if uploaded_file.type != "application/pdf":
                    img = Image.open(uploaded_file)
                    st.image(img, use_column_width=True)
                    uploaded_file.seek(0)  # Reset after reading
                else:
                    st.info("📄 PDF uploaded")

            with col2:
                st.markdown("**File Details:**")
                st.write(f"Name: `{uploaded_file.name}`")
                st.write(f"Type: `{uploaded_file.type}`")
                st.write(f"Size: `{uploaded_file.size / 1024:.1f} KB`")

                st.markdown("**Pipeline:**")
                st.markdown("1. 📸 OCR text extraction")
                st.markdown("2. 🧹 Clean & parse fields")
                st.markdown("3. 🤖 AI categorization")
                st.markdown("4. 🏦 Bank reconciliation")
                st.markdown("5. 📊 Export to Sheets/CSV")

            st.markdown("---")

            if st.button("🚀 Process Receipt", type="primary", use_container_width=True):
                # Save to temp file
                suffix = os.path.splitext(uploaded_file.name)[1]
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=suffix
                ) as tmp:
                    tmp.write(uploaded_file.read())
                    tmp_path = tmp.name

                with st.spinner("Processing your receipt..."):
                    result = run_pipeline(tmp_path, bank_df, sheets_enabled)

                os.unlink(tmp_path)

                if result:
                    # Show image for display
                    if uploaded_file.type != "application/pdf":
                        uploaded_file.seek(0)
                        display_img = Image.open(uploaded_file)
                    else:
                        display_img = None

                    display_results(result, display_img)

        else:
            # Empty state
            st.markdown("---")
            st.markdown(
                """
                <div style='text-align:center; padding: 3rem; 
                color: #888; border: 2px dashed #ddd; border-radius: 12px;'>
                    <h3>👆 Upload a receipt to get started</h3>
                    <p>Supports JPG, PNG, and PDF formats</p>
                </div>
                """,
                unsafe_allow_html=True
            )

    # ── Tab 2: Batch ──────────────────────────────────────────────
    with tab2:
        render_batch_tab(bank_df, sheets_enabled)

    # # ── Tab 3: History ────────────────────────────────────────────
    # with tab3:
    #     st.markdown("### 📊 Processing History")

    #     csv_path = "data/outputs/expenses.csv"
    #     if os.path.exists(csv_path):
    #         df = pd.read_csv(csv_path)
    #         st.caption(f"Showing {len(df)} processed receipts")

    #         # Summary metrics
    #         m1, m2, m3, m4 = st.columns(4)
    #         m1.metric("Total Records", len(df))

    #         if "Total Amount (Rs)" in df.columns:
    #             total = pd.to_numeric(df["Total Amount (Rs)"], errors="coerce").sum()
    #             m2.metric("Total Spend", f"Rs {total:,.2f}")

    #         if "Reconciliation Status" in df.columns:
    #             matched = df["Reconciliation Status"].str.contains("Matched", na=False).sum()
    #             m3.metric("Matched", matched)

    #         if "Category" in df.columns:
    #             top_cat = df["Category"].mode()[0] if len(df) > 0 else "—"
    #             m4.metric("Top Category", top_cat)

    #         st.markdown("---")
    #         st.dataframe(df, use_container_width=True, hide_index=True)

    #         # Download button
    #         with open(csv_path, "rb") as f:
    #             st.download_button(
    #                 "⬇️ Download Full CSV",
    #                 f,
    #                 file_name="expense_history.csv",
    #                 mime="text/csv"
    #             )
    #     else:
    #         st.info("No history yet — process some receipts first!")


if __name__ == "__main__":
    main()



