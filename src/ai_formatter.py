"""
src/ai_formatter.py
-------------------
Smart final-stage formatter for receipt extraction results.
CHATGPT 
Purpose:
Transforms messy OCR / parsed outputs into clean professional data.

Pipeline Position:
OCR -> text_cleaner -> categorizer -> ai_formatter -> app.py

Features:
- Vendor cleanup
- Date recovery / normalization
- Amount correction
- Premium category labels
- Confidence score
- Better display formatting
"""

import re
from datetime import datetime


# ─────────────────────────────────────────────
# KNOWN BUSINESS / HOSPITAL / BRAND CORRECTIONS
# ─────────────────────────────────────────────

KNOWN_NAMES = {
    "hiranandani": "Dr L H Hiranandani Hospital",
    "apollo": "Apollo Hospital",
    "fortis": "Fortis Hospital",
    "medanta": "Medanta Hospital",
    "starbucks": "Starbucks",
    "mcdonald": "McDonald's",
    "dominos": "Domino's",
    "zomato": "Zomato",
    "swiggy": "Swiggy",
    "amazon": "Amazon",
    "flipkart": "Flipkart",
    "dmart": "DMart",
    "reliance": "Reliance Retail",
    "indianoil": "Indian Oil",
    "hp petrol": "HP Petrol Pump",
    "shell": "Shell Petrol Pump",
}


# ─────────────────────────────────────────────
# CATEGORY BEAUTIFIER
# ─────────────────────────────────────────────

CATEGORY_MAP = {
    "Medical & Health": "Medical / Hospital / Healthcare",
    "Travel & Transport": "Travel / Transport",
    "Meals & Entertainment": "Food / Dining / Entertainment",
    "Shopping & Retail": "Shopping / Retail",
    "Fuel & Petrol": "Fuel / Petrol",
    "Software & Subscriptions": "Software / Subscription",
    "Office Supplies": "Office Supplies",
    "Communication": "Mobile / Internet / Telecom",
    "Accommodation": "Hotel / Accommodation",
    "Training & Education": "Training / Education",
    "Equipment & Hardware": "Equipment / Hardware",
    "Miscellaneous": "Other Expense",
}

# 
# ─────────────────────────────────────────────
# VENDOR CLEANUP
# ─────────────────────────────────────────────

def clean_vendor(vendor: str, raw_text: str = "") -> str:
    text = f"{vendor} {raw_text}".lower()

    # Known brand matching
    for key, value in KNOWN_NAMES.items():
        if key in text:
            return value

    # Remove junk chars
    vendor = re.sub(r"[^A-Za-z0-9\s&.-]", " ", vendor)
    vendor = re.sub(r"\s+", " ", vendor).strip()

    # Remove nonsense tiny words
    words = vendor.split()
    words = [w for w in words if len(w) > 1]

    vendor = " ".join(words)

    if not vendor:
        return "Unknown Vendor"

    return vendor.title()


# ─────────────────────────────────────────────
# DATE CLEANUP
# ─────────────────────────────────────────────

def clean_date(date_text: str, raw_text: str = "") -> str:
    text = f"{date_text} {raw_text}"

    patterns = [
        r"\b(\d{2}/\d{2}/\d{4})\b",
        r"\b(\d{2}-\d{2}-\d{4})\b",
        r"\b(\d{4}-\d{2}-\d{2})\b",
        r"\b(\d{2}\.\d{2}\.\d{4})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            found = match.group(1)

            for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"):
                try:
                    dt = datetime.strptime(found, fmt)
                    return dt.strftime("%d/%m/%Y")
                except:
                    pass

    return "Unknown Date"


# ─────────────────────────────────────────────
# AMOUNT CLEANUP
# ─────────────────────────────────────────────

def clean_amount(amount) -> str:
    try:
        amt = float(amount)
    except:
        return "₹0"

    # OCR sometimes adds extra zero: 64400 instead of 6400
    if amt >= 50000 and amt % 100 == 0:
        amt = amt / 10

    return f"₹{amt:,.0f}"


# ─────────────────────────────────────────────
# CATEGORY CLEANUP
# ─────────────────────────────────────────────

def clean_category(category: str) -> str:
    return CATEGORY_MAP.get(category, category)


# ─────────────────────────────────────────────
# CONFIDENCE SCORE
# ─────────────────────────────────────────────

def generate_confidence(vendor, date, amount):
    score = 0

    if vendor != "Unknown Vendor":
        score += 35

    if date != "Unknown Date":
        score += 30

    if amount != "₹0":
        score += 35

    return f"{score}%"


# ─────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────

def format_receipt_output(data: dict) -> dict:
    """
    Input:
        parsed + categorized receipt dict

    Output:
        clean final dict
    """

    raw_text = data.get("raw_text", "")

    vendor = clean_vendor(
        data.get("vendor_name", ""),
        raw_text
    )

    date = clean_date(
        data.get("date", ""),
        raw_text
    )

    amount = clean_amount(
        data.get("total_amount", 0)
    )

    category = clean_category(
        data.get("category", "Other Expense")
    )

    confidence = generate_confidence(vendor, date, amount)

    data["vendor_name"] = vendor
    data["date"] = date
    data["total_amount_display"] = amount
    data["category"] = category
    data["ai_confidence"] = confidence

    return data