"""test_ocr.py
-----------
Tests the OCR engine with a generated sample receipt.
Run this file directly to verify everything works.
"""

import sys
import os

# Add parent directory to path so we can import src/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont
from src.ocr_engine import extract_text


def create_sample_receipt(output_path: str):
    """
    Creates a fake receipt image for testing.
    Useful when you don't have a real receipt handy.
    """
    # Create white background
    img = Image.new("RGB", (600, 800), color="white")
    draw = ImageDraw.Draw(img)

    # Use default font (no installation needed)
    font = ImageFont.load_default()

    # Receipt content
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

    # Draw each line
    y = 40
    for line in lines:
        draw.text((30, y), line, fill="black", font=font)
        y += 24

    img.save(output_path)
    print(f"✅ Sample receipt created: {output_path}")
    return output_path


def run_test():
    print("\n" + "🧪 " * 20)
    print("RUNNING OCR ENGINE TEST")
    print("🧪 " * 20)

    # Create sample receipt
    receipt_path = "data/receipts/test_receipt.jpg"
    create_sample_receipt(receipt_path)

    # Run OCR on it
    result = extract_text(receipt_path)

    # Show results
    print("\n" + "=" * 50)
    print("📋 EXTRACTED TEXT:")
    print("=" * 50)
    print(result["text"])
    print("=" * 50)
    print(f"\n📊 Engine used : {result.get('engine', 'N/A')}")
    print(f"📊 Confidence  : {result.get('confidence', 0):.1f}%")
    print(f"📊 Characters  : {len(result.get('text', ''))}")

    # Basic validation
    print("\n🔍 Validation Checks:")
    checks = {
        "Contains store name": "QUICK MART" in result["text"].upper(),
        "Contains total amount": "1,280" in result["text"] or "1280" in result["text"],
        "Contains date": "2025" in result["text"],
        "Text is not empty": len(result["text"]) > 50,
    }

    all_passed = True
    for check, passed in checks.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {status} — {check}")
        if not passed:
            all_passed = False

    print("\n" + ("🎉 ALL TESTS PASSED!" if all_passed else "⚠️ SOME TESTS FAILED — check output above"))


if __name__ == "__main__":
    run_test()