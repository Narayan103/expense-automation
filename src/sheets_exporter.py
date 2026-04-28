"""
sheets_exporter.py
------------------
Exports processed receipt data to Google Sheets.

Features:
- Auto-creates headers on first run
- Appends new rows without overwriting
- Color codes rows by reconciliation status
- Handles API errors gracefully
"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

# Load environment variables from .env file
load_dotenv()


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

# Scopes tell Google what permissions we need
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Column headers for our sheet
HEADERS = [
    "Submission Date",
    "Vendor Name",
    "Expense Date",
    "Total Amount (Rs)",
    "Category",
    "Project Name",
    "Reconciliation Status",
    "Matched Bank Entry",
    "Transaction ID",
    "Match Confidence",
    "OCR Engine",
    "Category Method",
    "Raw File",
    "Notes"
]

# Colors for reconciliation status
STATUS_COLORS = {
    "matched"        : {"red": 0.85, "green": 0.95, "blue": 0.85},  # Light green
    "possible_match" : {"red": 1.0,  "green": 0.95, "blue": 0.80},  # Light yellow
    "unmatched"      : {"red": 1.0,  "green": 0.85, "blue": 0.85},  # Light red
    "default"        : {"red": 1.0,  "green": 1.0,  "blue": 1.0},   # White
}


# ─────────────────────────────────────────────
# STEP 1: AUTHENTICATION
# ─────────────────────────────────────────────

def get_google_client():
    """
    Authenticate with Google using service account credentials.

    Returns:
        Authenticated gspread client
    """
    creds_file = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

    if not os.path.exists(creds_file):
        raise FileNotFoundError(
            f"Credentials file not found: {creds_file}\n"
            "Please follow the Google Sheets setup instructions in README."
        )

    creds = Credentials.from_service_account_file(creds_file, scopes=SCOPES)
    client = gspread.authorize(creds)
    print("✅ Google Sheets authenticated successfully.")
    return client


# ─────────────────────────────────────────────
# STEP 2: SHEET SETUP
# ─────────────────────────────────────────────

def get_or_create_sheet(client):
    """
    Open the Google Sheet. Create headers if it's empty.

    Returns:
        gspread Worksheet object
    """
    sheet_id = os.getenv("GOOGLE_SHEETS_ID")

    if not sheet_id:
        raise ValueError(
            "GOOGLE_SHEETS_ID not set in .env file.\n"
            "Please add: GOOGLE_SHEETS_ID=your_sheet_id"
        )

    try:
        spreadsheet = client.open_by_key(sheet_id)
        sheet = spreadsheet.sheet1
        print(f"✅ Opened sheet: {spreadsheet.title}")
    except Exception as e:
        raise ConnectionError(f"Could not open Google Sheet: {e}")

    # Check if headers exist
    existing = sheet.row_values(1)

    if not existing or existing[0] != "Submission Date":
        print("📝 Adding headers to sheet...")
        sheet.insert_row(HEADERS, index=1)

        # Format header row - bold and colored
        sheet.format("A1:N1", {
            "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.8},
            "textFormat": {
                "bold": True,
                "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0},
                "fontSize": 11
            },
            "horizontalAlignment": "CENTER"
        })

        # Freeze header row
        spreadsheet.batch_update({
            "requests": [{
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet.id,
                        "gridProperties": {"frozenRowCount": 1}
                    },
                    "fields": "gridProperties.frozenRowCount"
                }
            }]
        })

        print("✅ Headers created and formatted.")

    return sheet


# ─────────────────────────────────────────────
# STEP 3: DATA FORMATTING
# ─────────────────────────────────────────────

def format_receipt_for_sheet(receipt: dict) -> list:
    """
    Convert a receipt dictionary into a flat row for Google Sheets.

    Args:
        receipt: Fully processed receipt dict

    Returns:
        List of values in the same order as HEADERS
    """
    # Format confidence as percentage string
    confidence = receipt.get("match_confidence", 0)
    confidence_str = f"{confidence:.0%}" if confidence else "N/A"

    # Format amount with 2 decimal places
    amount = receipt.get("total_amount", 0)
    amount_str = f"{amount:.2f}" if amount else "0.00"

    # Reconciliation status — make it human readable
    recon_status = receipt.get("reconciliation_status", "not_run")
    status_display = {
        "matched"        : "✅ Matched",
        "possible_match" : "⚠️ Review",
        "unmatched"      : "❌ Unmatched",
        "not_run"        : "⏳ Pending"
    }.get(recon_status, recon_status)

    row = [
        datetime.now().strftime("%Y-%m-%d %H:%M"),   # Submission Date
        receipt.get("vendor_name", "Unknown"),         # Vendor Name
        receipt.get("date", "Unknown"),                # Expense Date
        amount_str,                                    # Total Amount
        receipt.get("category", "Uncategorized"),      # Category
        receipt.get("project_name", "General"),        # Project Name
        status_display,                                # Reconciliation Status
        receipt.get("matched_bank_description", ""),   # Matched Bank Entry
        receipt.get("matched_transaction_id", ""),     # Transaction ID
        confidence_str,                                # Match Confidence
        receipt.get("ocr_engine", ""),                 # OCR Engine
        receipt.get("category_method", ""),            # Category Method
        receipt.get("file", ""),                       # Raw File
        receipt.get("notes", "")                       # Notes
    ]

    return row


# ─────────────────────────────────────────────
# STEP 4: COLOR CODING
# ─────────────────────────────────────────────

def apply_row_color(sheet, row_number: int, status: str):
    """
    Color-code a row based on reconciliation status.

    Green  = matched
    Yellow = possible match / needs review
    Red    = unmatched

    Args:
        sheet: gspread worksheet
        row_number: Row index (1-based)
        status: reconciliation_status string
    """
    color = STATUS_COLORS.get(status, STATUS_COLORS["default"])
    cell_range = f"A{row_number}:N{row_number}"

    try:
        sheet.format(cell_range, {
            "backgroundColor": color
        })
    except Exception as e:
        print(f"   ⚠️ Could not apply color: {e}")


# ─────────────────────────────────────────────
# STEP 5: EXPORT FUNCTIONS
# ─────────────────────────────────────────────

def export_receipt(receipt: dict) -> bool:
    """
    Export a single receipt to Google Sheets.

    Args:
        receipt: Fully processed receipt dictionary

    Returns:
        True if successful, False otherwise
    """
    print(f"\n📤 Exporting to Google Sheets...")

    try:
        # Authenticate and get sheet
        client = get_google_client()
        sheet  = get_or_create_sheet(client)

        # Format data as a row
        row = format_receipt_for_sheet(receipt)

        # Append the row
        sheet.append_row(row, value_input_option="USER_ENTERED")

        # Get the row number we just added
        all_values = sheet.get_all_values()
        new_row_num = len(all_values)

        # Color code based on reconciliation status
        status = receipt.get("reconciliation_status", "default")
        apply_row_color(sheet, new_row_num, status)

        print(f"✅ Exported successfully to row {new_row_num}!")
        print(f"   Vendor  : {receipt.get('vendor_name')}")
        print(f"   Amount  : Rs {receipt.get('total_amount')}")
        print(f"   Status  : {receipt.get('reconciliation_status')}")

        return True

    except FileNotFoundError as e:
        print(f"❌ Credentials error: {e}")
        return False
    except ConnectionError as e:
        print(f"❌ Connection error: {e}")
        return False
    except Exception as e:
        print(f"❌ Export failed: {e}")
        return False


def export_batch(receipts: list) -> dict:
    """
    Export multiple receipts to Google Sheets efficiently.

    Args:
        receipts: List of processed receipt dicts

    Returns:
        Summary dict with success/failure counts
    """
    print(f"\n📤 Batch exporting {len(receipts)} receipt(s)...")

    try:
        client = get_google_client()
        sheet  = get_or_create_sheet(client)

        success_count = 0
        fail_count    = 0

        for i, receipt in enumerate(receipts, 1):
            print(f"\n[{i}/{len(receipts)}] {receipt.get('vendor_name', 'Unknown')}")
            try:
                row = format_receipt_for_sheet(receipt)
                sheet.append_row(row, value_input_option="USER_ENTERED")

                all_values  = sheet.get_all_values()
                new_row_num = len(all_values)
                status      = receipt.get("reconciliation_status", "default")
                apply_row_color(sheet, new_row_num, status)

                print(f"   ✅ Row {new_row_num} added")
                success_count += 1

            except Exception as e:
                print(f"   ❌ Failed: {e}")
                fail_count += 1

        summary = {
            "total"    : len(receipts),
            "success"  : success_count,
            "failed"   : fail_count,
        }

        print(f"\n{'='*40}")
        print(f"📊 EXPORT SUMMARY")
        print(f"{'='*40}")
        print(f"  ✅ Success : {success_count}")
        print(f"  ❌ Failed  : {fail_count}")
        print(f"  📋 Total   : {len(receipts)}")

        return summary

    except Exception as e:
        print(f"❌ Batch export failed: {e}")
        return {"total": len(receipts), "success": 0, "failed": len(receipts)}


# ─────────────────────────────────────────────
# LOCAL CSV FALLBACK
# ─────────────────────────────────────────────

def export_to_csv(receipts: list, output_path: str = "data/outputs/expenses.csv"):
    """
    Fallback: export to local CSV if Google Sheets is unavailable.
    Useful for testing without internet or credentials.

    Args:
        receipts: List of processed receipt dicts
        output_path: Where to save the CSV
    """
    import pandas as pd

    print(f"\n💾 Exporting to local CSV: {output_path}")

    rows = [format_receipt_for_sheet(r) for r in receipts]
    df   = pd.DataFrame(rows, columns=HEADERS)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"✅ Saved {len(rows)} row(s) to {output_path}")
    return output_path