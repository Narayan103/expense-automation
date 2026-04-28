"""
test_ocr.py
-----------
Full pipeline test: OCR → Clean → Categorize → Reconcile
Run: python tests/test_ocr.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont
from src.ocr_engine import extract_text
from src.text_cleaner import parse_receipt
from src.categorizer import categorize_expense
from src.reconciler import load_bank_statement, reconcile


def create_sample_receipt(output_path: str):
    img = Image.new("RGB", (600, 800), color="white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    lines = [
        "================================",
        "        QUICK MART STORE        ",
        "     123 Main Street, Delhi     ",
        "       Tel: 011-2345-6789       ",
        "================================",
        "",
        "Date: 25-Apr-2025   Time: 14:32",
        "Bill No: QM-2025-00847",
        "",
        "--------------------------------",
        "ITEM              QTY    AMOUNT",
        "--------------------------------",
        "Office Pens        2     Rs 120",
        "Notebook A4        3     Rs 180",
        "Stapler            1     Rs 250",
        "Printer Paper      2     Rs 440",
        "Tea Bags Pack      1     Rs  95",
        "--------------------------------",
        "",
        "Subtotal:             Rs 1,085",
        "GST (18%):            Rs   195",
        "                    ----------",
        "TOTAL:                Rs 1,280",
        "",
        "Payment: Credit Card",
        "Card: **** **** **** 4521",
        "",
        "================================",
        "   Thank you for your visit!    ",
        "================================",
    ]

    y = 40
    for line in lines:
        draw.text((30, y), line, fill="black", font=font)
        y += 24

    img.save(output_path)
    print(f"✅ Sample receipt created: {output_path}")


def run_test():
    print("\n" + "🧪 " * 20)
    print("FULL PIPELINE: OCR → CLEAN → CATEGORIZE → RECONCILE")
    print("🧪 " * 20)

    receipt_path  = "data/receipts/test_receipt.jpg"
    bank_csv_path = "data/bank_statements/sample_bank.csv"

    create_sample_receipt(receipt_path)

    # Stage 1: OCR
    print("\n📸 STAGE 1: OCR")
    ocr_result = extract_text(receipt_path)

    # Stage 2: Clean & Parse
    print("\n🧹 STAGE 2: CLEAN & PARSE")
    parsed = parse_receipt(ocr_result)

    # Stage 3: Categorize
    print("\n🏷️  STAGE 3: CATEGORIZE")
    categorized = categorize_expense(parsed)

    # Stage 4: Reconcile
    print("\n🏦 STAGE 4: RECONCILE")
    bank_df = load_bank_statement(bank_csv_path)
    final   = reconcile(categorized, bank_df)

    # Final output
    print("\n" + "=" * 50)
    print("✅ COMPLETE PIPELINE OUTPUT:")
    print("=" * 50)

    display_fields = [
        "vendor_name", "date", "total_amount",
        "category", "category_method",
        "project_name",
        "reconciliation_status",
        "matched_bank_description",
        "matched_transaction_id",
        "match_confidence",
    ]
    for key in display_fields:
        print(f"  {key:<30}: {final.get(key, 'N/A')}")

    # Validation
    print("\n🔍 Validation Checks:")
    checks = {
        "Vendor extracted"        : final["vendor_name"] != "Unknown Vendor",
        "Date extracted"          : final["date"] != "Unknown Date",
        "Amount > 0"              : final["total_amount"] > 0,
        "Category assigned"       : final["category"] != "Uncategorized",
        "Reconciliation ran"      : "reconciliation_status" in final,
        "Transaction matched"     : final["reconciliation_status"] in
                                    ["matched", "possible_match"],
    }

    all_passed = True
    for check, passed in checks.items():
        icon = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {icon} — {check}")
        if not passed:
            all_passed = False

    print("\n" + ("🎉 ALL TESTS PASSED!" if all_passed
                  else "⚠️  SOME CHECKS FAILED — see above"))


if __name__ == "__main__":
    run_test()