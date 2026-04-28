"""
categorizer.py
--------------
Intelligently categorizes expenses using a 3-layer approach:
  Layer 1: Keyword matching (fast, rule-based)
  Layer 2: Claude AI via Anthropic API (smart, context-aware)
  Layer 3: Fuzzy fallback (always returns something)
"""

import re
import json
import urllib.request
import urllib.error
from rapidfuzz import fuzz


# ─────────────────────────────────────────────
# CATEGORY DEFINITIONS
# ─────────────────────────────────────────────

CATEGORIES = {
    "Office Supplies": [
        "pen", "pencil", "notebook", "stapler", "paper", "printer",
        "ink", "toner", "folder", "binder", "tape", "scissors",
        "marker", "highlighter", "envelope", "stationery", "cartridge",
        "whiteboard", "eraser", "clip", "file", "lamination"
    ],
    "Travel & Transport": [
        "uber", "ola", "taxi", "cab", "auto", "rickshaw", "bus",
        "train", "railway", "irctc", "flight", "airline", "airport",
        "fuel", "petrol", "diesel", "parking", "toll", "metro",
        "rapido", "indigo", "spicejet", "air india", "makemytrip"
    ],
    "Meals & Entertainment": [
        "restaurant", "cafe", "coffee", "swiggy", "zomato", "hotel",
        "food", "lunch", "dinner", "breakfast", "snack", "pizza",
        "burger", "biryani", "tea", "beverage", "canteen", "dhaba",
        "dominos", "mcdonalds", "kfc", "starbucks", "subway"
    ],
    "Software & Subscriptions": [
        "aws", "azure", "google cloud", "github", "gitlab", "slack",
        "zoom", "microsoft", "adobe", "figma", "notion", "jira",
        "confluence", "dropbox", "netflix", "spotify", "subscription",
        "license", "saas", "software", "app", "digital", "cloud",
        "hosting", "domain", "vpn", "antivirus"
    ],
    "Accommodation": [
        "hotel", "inn", "lodge", "hostel", "airbnb", "oyo", "resort",
        "guest house", "stay", "room", "suite", "booking", "treebo",
        "fabhotel", "accommodation", "night", "check-in"
    ],
    "Medical & Health": [
        "pharmacy", "medicine", "medical", "doctor", "hospital",
        "clinic", "health", "lab", "diagnostic", "apollo", "netmeds",
        "1mg", "pharmeasy", "chemist", "drug", "prescription",
        "consultation", "pathology", "blood test", "xray"
    ],
    "Communication": [
        "airtel", "jio", "vodafone", "bsnl", "vi", "recharge",
        "mobile", "phone", "broadband", "internet", "sim", "data",
        "postpaid", "prepaid", "telecom", "wifi", "router"
    ],
    "Equipment & Hardware": [
        "laptop", "computer", "monitor", "keyboard", "mouse",
        "headphone", "speaker", "charger", "cable", "hard disk",
        "pendrive", "ram", "ssd", "printer", "scanner", "webcam",
        "projector", "screen", "display", "hardware", "device"
    ],
    "Training & Education": [
        "course", "training", "workshop", "seminar", "conference",
        "udemy", "coursera", "book", "certification", "exam",
        "coaching", "tutorial", "learning", "education", "class"
    ],
    "Miscellaneous": []  # Catch-all — always last
}


# ─────────────────────────────────────────────
# LAYER 1: KEYWORD MATCHING
# ─────────────────────────────────────────────

def categorize_by_keywords(vendor: str, raw_text: str) -> tuple[str, float]:
    """
    Match vendor name and receipt text against keyword lists.

    Scoring system:
    - Each keyword match adds points
    - Vendor name match = 2x points (more reliable signal)
    - Return category with highest score

    Returns:
        Tuple of (category_name, confidence_0_to_1)
    """
    combined_text = f"{vendor} {raw_text}".lower()
    scores = {category: 0.0 for category in CATEGORIES}

    for category, keywords in CATEGORIES.items():
        if category == "Miscellaneous":
            continue

        for keyword in keywords:
            # Check in full text
            if keyword in combined_text:
                scores[category] += 1.0

            # Bonus: check vendor name specifically (stronger signal)
            if keyword in vendor.lower():
                scores[category] += 1.0

            # Fuzzy match for OCR errors (e.g. "Airte1" → "Airtel")
            vendor_similarity = fuzz.partial_ratio(keyword, vendor.lower())
            if vendor_similarity >= 85:
                scores[category] += 0.5

    # Find best category
    best_category = max(scores, key=scores.get)
    best_score = scores[best_category]

    if best_score == 0:
        return "Miscellaneous", 0.0

    # Normalize confidence to 0-1 range (cap at 1.0)
    confidence = min(best_score / 3.0, 1.0)

    return best_category, confidence


# ─────────────────────────────────────────────
# LAYER 2: CLAUDE AI CATEGORIZATION
# ─────────────────────────────────────────────

def categorize_by_ai(vendor: str, raw_text: str, amount: float) -> str:
    """
    Use Claude AI (via Anthropic API) to categorize the expense.
    Called only when keyword matching is not confident enough.

    This makes a real API call to Claude — completely free to use
    within claude.ai artifacts.

    Returns:
        Category string from CATEGORIES list
    """
    category_list = [c for c in CATEGORIES.keys() if c != "Miscellaneous"]

    # Build a focused prompt
    prompt = f"""You are an expense categorization assistant for a company.

Analyze this receipt and assign ONE category from the list below.

Receipt Details:
- Vendor: {vendor}
- Amount: {amount}
- Receipt Text (first 300 chars): {raw_text[:300]}

Available Categories:
{chr(10).join(f'- {cat}' for cat in category_list)}
- Miscellaneous

Rules:
1. Reply with ONLY the category name — nothing else
2. Choose the most specific matching category
3. Use "Miscellaneous" only if nothing fits

Category:"""

    try:
        # Call Anthropic API
        payload = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 50,
            "messages": [{"role": "user", "content": prompt}]
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            ai_response = data["content"][0]["text"].strip()

        # Validate the response is a known category
        for category in CATEGORIES.keys():
            if category.lower() in ai_response.lower():
                print(f"   🤖 AI categorized as: {category}")
                return category

        # If AI returned something unexpected, fall through
        print(f"   ⚠️ AI returned unknown category: {ai_response}")
        return None

    except Exception as e:
        print(f"   ⚠️ AI categorization failed: {e}")
        return None


# ─────────────────────────────────────────────
# LAYER 3: FUZZY FALLBACK
# ─────────────────────────────────────────────

def categorize_by_fuzzy(vendor: str, raw_text: str) -> str:
    """
    Last resort: fuzzy match vendor against category keywords.
    Always returns something — never fails.

    Returns:
        Best-guess category string
    """
    combined = f"{vendor} {raw_text}".lower()
    best_category = "Miscellaneous"
    best_score = 0

    for category, keywords in CATEGORIES.items():
        if category == "Miscellaneous":
            continue
        for keyword in keywords:
            score = fuzz.partial_ratio(keyword, combined)
            if score > best_score:
                best_score = score
                best_category = category

    # Only trust fuzzy if score is reasonably high
    if best_score < 60:
        return "Miscellaneous"

    return best_category


# ─────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────

def categorize_expense(parsed_receipt: dict) -> dict:
    """
    Master categorization function.
    Runs all 3 layers in sequence until confident.

    Args:
        parsed_receipt: Dictionary from text_cleaner.parse_receipt()

    Returns:
        Same dictionary with 'category' field filled in
    """
    vendor    = parsed_receipt.get("vendor_name", "")
    raw_text  = parsed_receipt.get("raw_text", "")
    amount    = parsed_receipt.get("total_amount", 0)

    print("\n🏷️  Categorizing expense...")
    print(f"   Vendor : {vendor}")
    print(f"   Amount : {amount}")

    # ── Layer 1: Keyword matching ─────────────────────────────────
    category, confidence = categorize_by_keywords(vendor, raw_text)
    print(f"   Layer 1 (Keywords) → {category} (confidence: {confidence:.0%})")

    if confidence >= 0.4:
        print(f"   ✅ Confident enough — using keyword result.")
        parsed_receipt["category"] = category
        parsed_receipt["category_method"] = "keywords"
        parsed_receipt["category_confidence"] = round(confidence, 2)
        return parsed_receipt

    # ── Layer 2: Claude AI ────────────────────────────────────────
    print(f"   ⚠️ Low confidence — escalating to AI...")
    ai_category = categorize_by_ai(vendor, raw_text, amount)

    if ai_category:
        parsed_receipt["category"] = ai_category
        parsed_receipt["category_method"] = "ai"
        parsed_receipt["category_confidence"] = 0.9
        return parsed_receipt

    # ── Layer 3: Fuzzy fallback ───────────────────────────────────
    print(f"   ⚠️ AI failed — using fuzzy fallback...")
    fuzzy_category = categorize_by_fuzzy(vendor, raw_text)
    print(f"   Layer 3 (Fuzzy) → {fuzzy_category}")

    parsed_receipt["category"] = fuzzy_category
    parsed_receipt["category_method"] = "fuzzy"
    parsed_receipt["category_confidence"] = 0.3
    return parsed_receipt