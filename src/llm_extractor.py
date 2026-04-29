"""
llm_extractor.py
----------------
LangChain + Gemini powered receipt data extractor.
Replaces regex-based extraction for messy/handwritten receipts.

Usage:
    from src.llm_extractor import extract_with_llm
    result = extract_with_llm(ocr_text)
"""

import os
import json
import re
from dotenv import load_dotenv

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
# from langchain.chains import LLMChain

load_dotenv()


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Category list — must match your existing categorizer.py
VALID_CATEGORIES = [
    "Office Supplies",
    "Travel & Transport",
    "Meals & Entertainment",
    "Software & Subscriptions",
    "Accommodation",
    "Medical & Health",
    "Communication",
    "Equipment & Hardware",
    "Training & Education",
    "Fuel & Petrol",
    "Newspaper & Media",
    "Shopping & Retail",
    "Miscellaneous"
]


# ─────────────────────────────────────────────
# PROMPT TEMPLATE
# ─────────────────────────────────────────────

RECEIPT_EXTRACTION_PROMPT = PromptTemplate(
    input_variables=["ocr_text", "categories"],
    template="""
You are an expert receipt data extraction assistant for an Indian company's expense system.

You will receive raw OCR text extracted from a receipt or invoice. The text may be:
- Messy or partially garbled (OCR errors)
- Mixed printed and handwritten content
- In various Indian receipt formats
- Containing irrelevant text, separators, watermarks

Your job is to extract the key fields and return ONLY a valid JSON object.

## RAW OCR TEXT:
{ocr_text}

## AVAILABLE CATEGORIES:
{categories}

## EXTRACTION RULES:
1. vendor_name: The business/store name. Clean up OCR errors. Title case.
2. date: Find the transaction/bill date. Convert to YYYY-MM-DD.
   - Look specifically after keywords: Date:, Dt., Dated, दिनांक
   - Indian format DD/MM/YYYY: "16/2/2026" → "2026-02-16"
   - "24/4/2026" → "2026-04-24"  
   - "16 | 2 | 2026" → "2026-02-16"
   - DO NOT confuse Bill No or Receipt No with the date
   - Bill No 101 is NOT a date
   - If year is clearly current era (2020-2030), use it as-is
   - Return null only if absolutely no date found
3. total_amount: The FINAL total paid. Return as number only.
   - For this receipt: look for "Total", "टोटल", "एकूण" (Marathi for total)
   - "2070/-" → 2070.0
   - "1500/-" → 1500.0  
   - Rupees in Words: "Two thousand seventy" → 2070.0
   - अक्षरी रुपये = amount in words in Marathi
   - IGNORE Bill No, Receipt No, Phone numbers (7+ digits)
   - Line items: 1890 + 180 = 2070 → use this if total unclear
   - Look for: TOTAL, Grand Total, Sale, Net Payable, Amount Due
   - IMPORTANT: OCR often duplicates digits. "64400" on a receipt
     showing "6400" is a common error — if a 5-digit number starts
     with a repeated digit (like 6→64400), the real value is the
     4-digit version (6400). Always prefer amounts that match the
     sum of visible line items.
   - Line items visible: Registration 200, Consultation 1000,
     Covid Test 4500, Handling 700 → sum = 6400 → trust this
   - "6400/-" → 6400.0
   - "64400" where line items sum to 6400 → return 6400.0
   - Return 0 if truly not found
4. currency: Default "INR" for Indian receipts
5. category: Pick ONE from the available categories that best fits
6. items: List of individual line items if visible. Each item has:
   - name: item description
   - amount: item amount as number
   If no items visible, return empty list []
7. payment_method: Cash/Card/UPI/COD if visible, else null
8. confidence: Your confidence in the extraction (low/medium/high)
9. notes: Any important observations about OCR quality or missing data

## RESPONSE FORMAT (return ONLY this JSON, no explanation):
{{
  "vendor_name": "string",
  "date": "YYYY-MM-DD or null",
  "total_amount": number,
  "currency": "INR",
  "category": "string from category list",
  "items": [
    {{"name": "string", "amount": number}}
  ],
  "payment_method": "string or null",
  "confidence": "low|medium|high",
  "notes": "string"
}}
"""
)


# ─────────────────────────────────────────────
# LLM SETUP
# ─────────────────────────────────────────────

def _get_llm():
    """
    Initialize Gemini LLM via LangChain.
    Uses gemini-1.5-flash (free tier: 1500 requests/day).
    """
    if not GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY not found in .env file.\n"
            "Get your free key at: https://aistudio.google.com/app/apikey"
        )

    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash-lite",
        google_api_key=GEMINI_API_KEY,
        temperature=0.1,      # Low temperature = more consistent output
        max_tokens=1024,
    )


# ─────────────────────────────────────────────
# MAIN EXTRACTION FUNCTION
# ─────────────────────────────────────────────

def extract_with_llm(ocr_text: str) -> dict:
    """
    Use LangChain + Gemini to extract structured data from raw OCR text.

    This is smarter than regex — it understands context, handles typos,
    and can infer values even from messy OCR output.

    Args:
        ocr_text: Raw text string from ocr_engine.extract_text()

    Returns:
        Structured dictionary with all receipt fields
    """
    print("\n🤖 Running LLM extraction (Gemini)...")

    if not ocr_text or len(ocr_text.strip()) < 10:
        print("   ⚠️ OCR text too short for LLM extraction")
        return _empty_result("OCR text too short")

    try:
        # Build the chain
        llm   = _get_llm()
        # Modern LangChain syntax (RunnableSequence)
        chain = RECEIPT_EXTRACTION_PROMPT | llm

        categories_str = "\n".join(f"- {c}" for c in VALID_CATEGORIES)
        response = chain.invoke({
            "ocr_text"  : ocr_text[:3000],
            "categories": categories_str
        })

        # New syntax returns AIMessage object, not dict
        raw_response = response.content if hasattr(response, "content") else str(response)
        print(f"   📥 LLM responded ({len(raw_response)} chars)")

        # Parse JSON from response
        result = _parse_llm_response(raw_response)

        if result:
            print(f"   ✅ LLM extraction successful")
            print(f"      Vendor   : {result.get('vendor_name')}")
            print(f"      Date     : {result.get('date')}")
            print(f"      Amount   : {result.get('total_amount')}")
            print(f"      Category : {result.get('category')}")
            print(f"      Confidence: {result.get('confidence')}")
            return result

        print("   ⚠️ Could not parse LLM response as JSON")
        return _empty_result("JSON parse failed")

    except Exception as e:
        print(f"   ❌ LLM extraction failed: {e}")
        return _empty_result(str(e))


# ─────────────────────────────────────────────
# RESPONSE PARSER
# ─────────────────────────────────────────────

def _parse_llm_response(raw: str) -> dict:
    """
    Safely parse JSON from LLM response.
    Handles cases where LLM adds markdown code fences.
    """
    if not raw:
        return {}

    # Remove markdown code fences if present
    # LLMs sometimes wrap JSON in ```json ... ```
    clean = re.sub(r'```(?:json)?', '', raw).strip()
    clean = clean.strip('`').strip()

    # Find JSON object in the response
    json_match = re.search(r'\{.*\}', clean, re.DOTALL)
    if not json_match:
        return {}

    try:
        data = json.loads(json_match.group(0))

        # Validate and sanitize fields
        return {
            "vendor_name"   : str(data.get("vendor_name", "Unknown Vendor")).strip(),
            "date"          : _validate_date(data.get("date")),
            "total_amount"  : _validate_amount(data.get("total_amount")),
            "currency"      : data.get("currency", "INR"),
            "category"      : _validate_category(data.get("category")),
            "items"         : data.get("items", []),
            "payment_method": data.get("payment_method"),
            "confidence"    : data.get("confidence", "medium"),
            "notes"         : data.get("notes", ""),
            "extraction_method": "llm_gemini"
        }

    except json.JSONDecodeError as e:
        print(f"   ⚠️ JSON decode error: {e}")
        return {}


def _validate_date(date_val) -> str:
    """Ensure date is in YYYY-MM-DD format or return 'Unknown Date'."""
    if not date_val or date_val == "null":
        return "Unknown Date"
    date_str = str(date_val).strip()
    # Check if it matches YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        return date_str
    return "Unknown Date"


def _validate_amount(amount_val) -> float:
    """Ensure amount is a valid positive float."""
    try:
        val = float(str(amount_val).replace(',', ''))
        return val if val >= 0 else 0.0
    except (ValueError, TypeError):
        return 0.0


def _validate_category(cat_val) -> str:
    """Ensure category is from our valid list."""
    if not cat_val:
        return "Miscellaneous"
    cat_str = str(cat_val).strip()
    # Exact match
    if cat_str in VALID_CATEGORIES:
        return cat_str
    # Partial match
    for valid_cat in VALID_CATEGORIES:
        if cat_str.lower() in valid_cat.lower() or valid_cat.lower() in cat_str.lower():
            return valid_cat
    return "Miscellaneous"


def _empty_result(reason: str) -> dict:
    """Return empty result when LLM fails."""
    return {
        "vendor_name"      : "Unknown Vendor",
        "date"             : "Unknown Date",
        "total_amount"     : 0.0,
        "currency"         : "INR",
        "category"         : "Miscellaneous",
        "items"            : [],
        "payment_method"   : None,
        "confidence"       : "low",
        "notes"            : f"LLM extraction failed: {reason}",
        "extraction_method": "llm_failed"
    }