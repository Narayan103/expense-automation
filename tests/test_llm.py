"""
test_llm.py
-----------
Tests LangChain + Gemini integration.
Run: python tests/test_llm.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from src.llm_extractor import extract_with_llm

# Simulate messy OCR output (like what EasyOCR produces)
MESSY_OCR_SAMPLE = """
Nc i
4 Hlronondani Hoenital
Dr L H Hiranandani Hospital
Your FaMily Superspeclality Hospital
Receipt 64985
BILcum Cash Receipt
Doror: D UmaLPeAjqdpt
Date : 15/09/2020
Dederuewon  Coet
Registration  900/-
Concultation chargesk  1000/-
Covid Test  4500/-
Handling chargesk  700/-
Total Amount in words Rupees
TOTAL  6400/-
Billing in-charge Administrator
"""

def run_test():
    print("\n" + "🧪 " * 20)
    print("LLM EXTRACTOR TEST (LangChain + Gemini)")
    print("🧪 " * 20)

    # Check API key
    if not os.getenv("GEMINI_API_KEY"):
        print("❌ GEMINI_API_KEY not set in .env")
        print("   Get your free key: https://aistudio.google.com/app/apikey")
        return

    print("\n📤 Sending messy OCR text to Gemini...")
    result = extract_with_llm(MESSY_OCR_SAMPLE)

    print("\n" + "="*50)
    print("✅ EXTRACTED RESULT:")
    print("="*50)
    for key, val in result.items():
        if key != "items":
            print(f"  {key:<20}: {val}")

    if result.get("items"):
        print(f"  {'items':<20}:")
        for item in result["items"]:
            print(f"    - {item.get('name')}: Rs {item.get('amount')}")

    # Validation
    print("\n🔍 Validation:")
    checks = {
        "Vendor correct"   : "hiranandani" in result.get("vendor_name","").lower(),
        "Date correct"     : result.get("date") == "2020-09-15",
        "Amount correct"   : result.get("total_amount") == 6400.0,
        "Category correct" : result.get("category") == "Medical & Health",
        "Has items"        : len(result.get("items", [])) > 0,
        "High confidence"  : result.get("confidence") in ["medium","high"],
    }

    all_passed = True
    for check, passed in checks.items():
        icon = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {icon} — {check}")
        if not passed:
            all_passed = False

    print("\n" + ("🎉 ALL TESTS PASSED!" if all_passed else "⚠️ Some failed — check above"))

if __name__ == "__main__":
    run_test()