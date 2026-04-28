"""
test_sheets.py
--------------
Tests Google Sheets export (and CSV fallback).
Run: python tests/test_sheets.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.sheets_exporter import export_to_csv, export_receipt, HEADERS


def get_mock_receipt():
    """A fully processed receipt — simulates the full pipeline output."""
    return {
        "vendor_name"               : "Quick Mart Store",
        "date"                      : "2025-04-25",
        "total_amount"              : 1280.0,
        "category"                  : "Office Supplies",
        "category_method"           : "keywords",
        "category_confidence"       : 0.8,
        "project_name"              : "General",
        "reconciliation_status"     : "matched",
        "matched_bank_description"  : "QUICK MART STORE DELHI",
        "matched_transaction_id"    : "TXN001",
        "match_confidence"          : 0.8,
        "ocr_engine"                : "tesseract",
        "file"                      : "data/receipts/test_receipt.jpg",
        "raw_text"                  : "Sample OCR text...",
        "status"                    : "success",
        "notes"                     : ""
    }


def test_csv_export():
    """Test local CSV export (no Google credentials needed)."""
    print("\n" + "="*50)
    print("TEST 1: CSV EXPORT (No credentials needed)")
    print("="*50)

    receipts = [get_mock_receipt()]
    output   = export_to_csv(receipts, "data/outputs/test_export.csv")

    # Validate
    assert os.path.exists(output), "CSV file was not created"

    import pandas as pd
    df = pd.read_csv(output)

    checks = {
        "CSV file created"          : os.path.exists(output),
        "Correct number of columns" : len(df.columns) == len(HEADERS),
        "One data row exists"       : len(df) == 1,
        "Vendor name correct"       : df.iloc[0]["Vendor Name"] == "Quick Mart Store",
        "Amount correct" : float(df.iloc[0]["Total Amount (Rs)"]) == 1280.0,
        "Status shows matched"      : "Matched" in str(df.iloc[0]["Reconciliation Status"]),
    }

    print("\n🔍 Validation Checks:")
    all_passed = True
    for check, passed in checks.items():
        icon = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {icon} — {check}")
        if not passed:
            all_passed = False

    return all_passed


def test_google_sheets_export():
    """Test actual Google Sheets export (requires credentials)."""
    print("\n" + "="*50)
    print("TEST 2: GOOGLE SHEETS EXPORT")
    print("="*50)

    # Check if credentials exist
    if not os.path.exists("credentials.json"):
        print("⚠️  credentials.json not found — skipping Google Sheets test.")
        print("   Complete the Google Cloud setup first.")
        return None

    if not os.getenv("GOOGLE_SHEETS_ID"):
        print("⚠️  GOOGLE_SHEETS_ID not set in .env — skipping.")
        return None

    receipt = get_mock_receipt()
    success = export_receipt(receipt)

    print("\n🔍 Validation:")
    if success:
        print("   ✅ PASS — Row exported to Google Sheets")
        print("   👉 Check your Google Sheet to see the new row!")
    else:
        print("   ❌ FAIL — Export failed (check error above)")

    return success


if __name__ == "__main__":
    print("\n" + "🧪 " * 20)
    print("GOOGLE SHEETS EXPORTER TESTS")
    print("🧪 " * 20)

    # Test 1: Always runs (no credentials needed)
    csv_passed = test_csv_export()

    # Test 2: Only runs if credentials are set up
    from dotenv import load_dotenv
    load_dotenv()
    sheets_result = test_google_sheets_export()

    # Summary
    print("\n" + "="*50)
    print("FINAL SUMMARY")
    print("="*50)
    print(f"  CSV Export    : {'✅ PASSED' if csv_passed else '❌ FAILED'}")
    print(f"  Google Sheets : {'✅ PASSED' if sheets_result else '⚠️  SKIPPED (no credentials yet)' if sheets_result is None else '❌ FAILED'}")

    if csv_passed:
        print("\n🎉 Core export working! Check data/outputs/test_export.csv")