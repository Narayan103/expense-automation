"""
test_ocr.py
-----------
Tests OCR engine + text cleaner together.
Run: python tests/test_ocr.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont
from src.ocr_engine import extract_text
from src.text_cleaner import parse_receipt, clean_raw_text


def create_sample_receipt(output_path: str):
    """Creates a fake receipt image for testing."""
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
    print("RUNNING FULL PIPELINE TEST (OCR + CLEANER)")
    print("🧪 " * 20)

    receipt_path = "data/receipts/test_receipt.jpg"
    create_sample_receipt(receipt_path)

    # Stage 1: OCR
    print("\n📸 STAGE 1: OCR EXTRACTION")
    ocr_result = extract_text(receipt_path)

    # Stage 2: Text Cleaning & Parsing
    print("\n🧹 STAGE 2: TEXT CLEANING & PARSING")
    parsed = parse_receipt(ocr_result)

    # Show final structured output
    print("\n" + "=" * 50)
    print("✅ FINAL STRUCTURED OUTPUT:")
    print("=" * 50)
    for key, value in parsed.items():
        if key != "raw_text":  # Skip raw text for cleaner display
            print(f"  {key:<15}: {value}")

    # Validation checks
    print("\n🔍 Validation Checks:")
    checks = {
        "Vendor extracted"      : parsed["vendor_name"] != "Unknown Vendor",
        "Date extracted"        : parsed["date"] != "Unknown Date",
        "Amount > 0"            : parsed["total_amount"] > 0,
        "Amount is 1280"        : abs(parsed["total_amount"] - 1280.0) < 1.0,
        "Status is success"     : parsed["status"] == "success",
    }

    all_passed = True
    for check, passed in checks.items():
        icon = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {icon} — {check}")
        if not passed:
            all_passed = False

    print("\n" + ("🎉 ALL TESTS PASSED!" if all_passed else "⚠️  SOME TESTS FAILED — check output above"))


if __name__ == "__main__":
    run_test()