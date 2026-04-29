"""
text_cleaner.py
---------------
Cleans raw OCR text and extracts structured fields:
- Vendor name
- Date
- Total amount
- Project name

Works even with messy, imperfect OCR output.
"""

import re
from datetime import datetime
from rapidfuzz import fuzz


# ─────────────────────────────────────────────
# STEP 1: RAW TEXT CLEANING
# ─────────────────────────────────────────────

def clean_raw_text(text: str) -> str:
    """
    Fix common OCR mistakes before we try to extract data.

    Common OCR errors:
    - '0' (zero) mistaken for 'O' (letter)
    - '1' mistaken for 'l' or 'I'
    - Extra spaces, weird symbols
    - Inconsistent line breaks

    Args:
        text: Raw string from OCR engine

    Returns:
        Cleaned string
    """
    if not text:
        return ""

    # Fix common OCR character confusions in NUMBER contexts
    # e.g. "2O25" → "2025", "1,28O" → "1,280"
    # Strategy: if surrounded by digits, O→0 and l→1
    text = re.sub(r'(?<=\d)O(?=\d)', '0', text)   # 2O25 → 2025
    text = re.sub(r'(?<=\d)o(?=\d)', '0', text)   # 2o25 → 2025
    text = re.sub(r'(?<=\d)l(?=\d)', '1', text)   # 1l80 → 1180
    text = re.sub(r'(?<=\d)I(?=\d)', '1', text)   # 1I80 → 1180

    # Remove non-printable/strange characters (keep basic ASCII)
    text = re.sub(r'[^\x20-\x7E\n]', ' ', text)

    # Normalize multiple spaces to single space
    text = re.sub(r'[ \t]+', ' ', text)

    # Normalize multiple blank lines to one
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Strip each line
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(lines)

    return text.strip()


# ─────────────────────────────────────────────
# STEP 2: VENDOR NAME EXTRACTION
# ─────────────────────────────────────────────

def extract_vendor(text: str) -> str:
    """
    Extract vendor name — improved to handle:
    - Hospital names spanning multiple words
    - Names after logos (Flipkart, IndianOil)
    - Avoiding garbage OCR lines at top
    """
    lines = text.strip().splitlines()

    skip_patterns = [
        r'^\s*$',                        # Empty lines
        r'={3,}|-{3,}|\*{3,}',          # Separator lines
        r'@|http|www\.',                 # URLs/emails
        r'gst|gstin|pan\s*:',           # Tax identifiers
        r'invoice\s*no|bill\s*no|receipt\s*no',  # Bill numbers
        r'date\s*:|time\s*:',           # Date/time lines
        r'thank\s*you',                  # Footer
        r'^\d+$',                        # Pure numbers
        r'mobile\s*|phone\s*|tel\s*',   # Contact info
        r'floor|street|road|nagar|colony|mumbai|delhi|bangalore',  # Addresses
        r'payment\s*receipt|cash\s*receipt',  # Receipt type labels
        r'cc\d{5,}',                     # Order codes like CC001427T3
    ]

    # Known vendor indicators — if we see these, grab them directly
    known_brands = [
        'flipkart', 'amazon', 'indianoil', 'indian oil', 'hp petrol',
        'bharat petroleum', 'reliance', 'swiggy', 'zomato', 'uber',
        'hiranandani', 'apollo', 'fortis', 'airtel', 'jio'
    ]

    full_text_lower = text.lower()
    for brand in known_brands:
        if brand in full_text_lower:
            # Find the actual line containing this brand
            for line in lines[:15]:
                if brand in line.lower():
                    clean = re.sub(r'[^a-zA-Z0-9\s&\'\-\.]', '', line)
                    clean = clean.strip()
                    clean = re.sub(r'^([A-Za-z])\1', r'\1', clean)
                    if len(clean) >= 3:
                        return clean.title()

    # General extraction — scan first 10 lines
    for line in lines[:10]:
        line = line.strip()

        if len(line) < 3:
            continue

        should_skip = any(
            re.search(p, line, re.IGNORECASE)
            for p in skip_patterns
        )
        if should_skip:
            continue

        # Must have at least 2 alphabet characters
        if len(re.findall(r'[a-zA-Z]', line)) < 2:
            continue

        clean = re.sub(r'[^a-zA-Z0-9\s&\'\-\.]', '', line)
        clean = clean.strip()

        if len(clean) >= 3:
            return clean.title()

    return "Unknown Vendor"


# ─────────────────────────────────────────────
# STEP 3: DATE EXTRACTION
# ─────────────────────────────────────────────

def extract_date(text: str) -> str:
    """
    Extract and standardize date from receipt text.
    Handles many Indian receipt formats.
    """
    month_map = {
        'jan':'01','feb':'02','mar':'03','apr':'04',
        'may':'05','jun':'06','jul':'07','aug':'08',
        'sep':'09','oct':'10','nov':'11','dec':'12',
        'january':'01','february':'02','march':'03','april':'04',
        'june':'06','july':'07','august':'08','september':'09',
        'october':'10','november':'11','december':'12'
    }

    # Only search lines that actually contain date hints
    date_hint_lines = []
    for line in text.splitlines():
        if re.search(r'date|dt\.?|dated|dо|do\b', line, re.IGNORECASE):
            date_hint_lines.append(line)
        elif re.search(r'\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}', line):
            date_hint_lines.append(line)

    # Search hint lines first, then full text as fallback
    search_targets = date_hint_lines + [text]

    for target in search_targets:

        # Pattern 0: "Date: 5/1/2012" or "Date Do 06/04/2022"
        # Looks specifically after the word "date"
        match = re.search(
            r'date\s*(?:do|:|-|\.|\s)\s*(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})',
            target, re.IGNORECASE
        )
        if match:
            day, month, year = match.groups()
            return f"{_fix_year(year)}-{month.zfill(2)}-{day.zfill(2)}"

        # Pattern 1: DD-Mon-YYYY e.g. "25-Apr-2025"
        match = re.search(
            r'\b(\d{1,2})[-/\s]([a-zA-Z]{3,9})[-/\s](\d{2,4})\b',
            target, re.IGNORECASE
        )
        if match:
            day, month_str, year = match.groups()
            month = month_map.get(month_str.lower())
            if month:
                return f"{_fix_year(year)}-{month}-{day.zfill(2)}"

        # Pattern 2: DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY
        match = re.search(
            r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})\b',
            target
        )
        if match:
            day, month, year = match.groups()
            year_int = int(_fix_year(year))
            month_int = int(month)
            day_int = int(day)
            # Validate: month must be 1-12, day 1-31
            if 1 <= month_int <= 12 and 1 <= day_int <= 31:
                return f"{_fix_year(year)}-{month.zfill(2)}-{day.zfill(2)}"

        # Pattern 3: "15/09/2020" anywhere in text
        match = re.search(r'\b(\d{2})/(\d{2})/(\d{4})\b', target)
        if match:
            day, month, year = match.groups()
            if 1 <= int(month) <= 12:
                return f"{year}-{month}-{day}"

        # Pattern 4: ISO format 2025-04-25
        match = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', target)
        if match:
            return match.group(0)

    return "Unknown Date"

def _fix_year(year: str) -> str:
    """Convert 2-digit year to 4-digit. '25' → '2025'"""
    if len(year) == 2:
        year_int = int(year)
        return f"20{year}" if year_int <= 50 else f"19{year}"
    return year


# ─────────────────────────────────────────────
# STEP 4: AMOUNT EXTRACTION
# ─────────────────────────────────────────────
def extract_amount(text: str) -> float:
    """
    Extract TOTAL amount using targeted strategies.
    Handles: 6400/- | 209. | 4516.14 | 142 00 (split by OCR)
    """
    lines = text.splitlines()

    # Words near total amount lines
    total_triggers = [
        "grand total", "total amount", "net payable", "total payable",
        "amount due", "net amount", "sale", "total"
    ]

    # Lines to never extract amount from
    skip_triggers = [
        "subtotal", "sub total", "rate", "price per", "density",
        "receipt no", "bill no", "tin ", "pan ", "mobile",
        "phone", "tel:", "gstin", "trans.id", "fp.id",
        "account", "balance brought", "no.:", "qty"
    ]

    # ── Strategy 1: Total keyword lines ───────────────────────────
    for keyword in total_triggers:
        for line in lines:
            line_lower = line.lower().strip()

            if any(skip in line_lower for skip in skip_triggers):
                continue

            if fuzz.partial_ratio(keyword, line_lower) >= 82:
                amount = _parse_amount_from_line(line)
                if 1 < amount < 500000:
                    print(f"   💡 Amount via '{keyword}': {amount}")
                    return amount
                # ── Strategy 1.5: Total value on NEXT line ───────────────────
    # Handles: "TOTAL\n6400/-" split across lines by OCR
    for i, line in enumerate(lines):
        if fuzz.partial_ratio("total", line.lower()) >= 85:
            # Check next 1-2 lines for the amount
            for next_line in lines[i+1 : i+3]:
                amount = _parse_amount_from_line(next_line)
                if 10 < amount < 500000:
                    print(f"   💡 Amount on line after TOTAL: {amount}")
                    return amount

    # ── Strategy 2: ₹ symbol lines ────────────────────────────────
    for line in lines:
        if '₹' not in line and 'rs' not in line.lower():
            continue

        line_lower = line.lower()
        if any(skip in line_lower for skip in skip_triggers):
            continue

        amount = _parse_amount_from_line(line)
        if 10 < amount < 500000:
            print(f"   💡 Amount via ₹ line: {amount}")
            return amount
        
# ── Strategy 2.5: Sum line items (for handwritten totals) ────
    # When total is handwritten and OCR fails, add up individual
    # charge lines instead. Looks for patterns like "200/-" "1000/-"
    line_item_amounts = []
    for line in lines:
        line_lower = line.lower().strip()

        # Skip header/footer lines
        if any(skip in line_lower for skip in skip_triggers):
            continue

        # Skip lines that are clearly labels not amounts
        if any(w in line_lower for w in [
            'total', 'subtotal', 'balance', 'grand',
            'service', 'tax', 'gst', 'discount'
        ]):
            continue

        # Look for lines with a single amount (like "200/-" or "1000/")
        amount = _parse_amount_from_line(line)
        if 50 < amount < 50000:  # Plausible line-item range
            line_item_amounts.append(amount)

    if len(line_item_amounts) >= 2:  # At least 2 items = likely real
        total = sum(line_item_amounts)
        if 10 < total < 500000:
            print(f"   💡 Amount via line-item sum ({len(line_item_amounts)} items): {total}")
            return total
        
    # ── Strategy 3: Amount in words ───────────────────────────────
    words_match = re.search(
        r'amount\s+in\s+words[^a-zA-Z]{0,5}([A-Za-z\s]+?)(?:only|rupees\s*$)',
        text, re.IGNORECASE
    )
    if words_match:
        word_amount = _words_to_number(words_match.group(1))
        if word_amount > 0:
            print(f"   💡 Amount via words: {word_amount}")
            return word_amount

    # ── Strategy 4: Money-context lines only ──────────────────────
    money_words = ['total','amount','paid','charge','cost','fee','sale']
    for line in lines:
        line_lower = line.lower()
        if not any(w in line_lower for w in money_words):
            continue
        if any(skip in line_lower for skip in skip_triggers):
            continue
        amount = _parse_amount_from_line(line)
        if 10 < amount < 500000:
            print(f"   💡 Amount via money context: {amount}")
            return amount

    print("   ⚠️ Amount not found")
    return 0.0


def _parse_amount_from_line(line: str) -> float:
    """
    Robustly extract monetary amount from one line.

    Handles all these real OCR outputs:
      '6400/-'        → 6400.0
      'TOTAL  209.'   → 209.0
      '₹ 4,516.14'   → 4516.14
      '142 00'        → 142.0   (OCR splits "142.00" into "142 00")
      '1,280'         → 1280.0
      '900/-'         → 900.0
    """
    original = line

    # Step 1: Remove currency symbols
    # Remove common OCR garbage characters that aren't numbers
    line = re.sub(r'[ZzOo~\{\}\[\]\\]', '', line)
    line = re.sub(r'[₹$€£]', ' ', line)
    line = re.sub(r'\bRs\.?\b', ' ', line, flags=re.IGNORECASE)
    line = re.sub(r'\bINR\b', ' ', line, flags=re.IGNORECASE)

    # Step 2: Remove trailing /- (Indian notation: 6400/-)
    line = re.sub(r'/-', ' ', line)
    # Fix Tesseract digit duplication error
    # "64400" where actual value is "6400" — first digit duplicated
    # Pattern: 5-digit number where digit[0] == digit[1]
    def fix_duplicate_digit(m):
        n = m.group(0)
        if len(n) == 5 and n[0] == n[1]:
            corrected = n[1:]  # Remove first duplicated digit
            print(f"   🔧 Corrected OCR digit duplication: {n} → {corrected}")
            return corrected
        return n

    line = re.sub(r'\b\d{5}\b', fix_duplicate_digit, line)

    # Step 3: Remove trailing dots
    line = line.rstrip('.')

    # Step 4: Handle OCR splitting decimals with space
    # "142 00" → "142.00", "4516 14" → "4516.14"
    line = re.sub(r'(\d+)\s+(\d{2})\b', r'\1.\2', line)

    # Step 5: Extract all valid number patterns
    # Matches: 6400, 4,516.14, 142.00, 1280
    numbers = re.findall(r'\b\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\b|\b\d{1,6}(?:\.\d{1,2})?\b', line)

    if not numbers:
        return 0.0

    parsed = []
    for n in numbers:
        try:
            val = float(n.replace(',', ''))
            # Must be a plausible amount (Rs 5 to Rs 5,00,000)
            if 5 <= val <= 500000:
                parsed.append(val)
        except ValueError:
            continue

    if not parsed:
        return 0.0

    # Return the largest plausible amount on this line
    return max(parsed)


def _words_to_number(text: str) -> float:
    """Convert English number words → integer. 'Two Hundred Nine' → 209"""
    word_map = {
        'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,
        'six':6,'seven':7,'eight':8,'nine':9,'ten':10,
        'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,
        'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,
        'nineteen':19,'twenty':20,'thirty':30,'forty':40,
        'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90,
        'hundred':100,'thousand':1000,'lakh':100000,'lac':100000
    }
    text = re.sub(r'[^a-zA-Z\s]', ' ', text.lower())
    words = text.split()
    total = 0
    current = 0
    for word in words:
        if word in ('and', 'only', 'rupees', 'rs', 'paise'):
            continue
        val = word_map.get(word, -1)
        if val == -1:
            continue
        if val == 100:
            current = (current or 1) * 100
        elif val in (1000, 100000):
            total += (current or 1) * val
            current = 0
        else:
            current += val
    total += current
    return float(total) if total > 0 else 0.0

# ─────────────────────────────────────────────
# STEP 5: PROJECT NAME EXTRACTION
# ─────────────────────────────────────────────

def extract_project(text: str) -> str:
    """
    Try to extract a project name from receipt text.

    In real usage, employees write the project name on the receipt
    or in the filename. We check both.

    Strategy:
    - Look for patterns like "Project: Alpha" in the text
    - Check if filename contains a project hint
    - Default to "General" if not found

    Returns:
        Project name string
    """
    # Pattern: "Project: XYZ" or "Proj: XYZ" or "For: XYZ"
    patterns = [
        r'project\s*[:\-]\s*([A-Za-z0-9\s]+)',
        r'proj\s*[:\-]\s*([A-Za-z0-9\s]+)',
        r'for\s+project\s*[:\-]\s*([A-Za-z0-9\s]+)',
        r'cost\s*center\s*[:\-]\s*([A-Za-z0-9\s]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            project = match.group(1).strip()
            if len(project) >= 2:
                return project.title()

    return "General"


# ─────────────────────────────────────────────
# MAIN FUNCTION
# ─────────────────────────────────────────────

def parse_receipt(ocr_result: dict, use_llm: bool = True) -> dict:
    """
    Master function: takes OCR result, returns structured data.
    Now supports LLM-powered extraction as primary method.
    """
    raw_text = ocr_result.get("text", "")

    # ── Try LLM extraction first ──────────────────────────────────
    if use_llm and raw_text:
        try:
            from src.llm_extractor import extract_with_llm
            llm_result = extract_with_llm(raw_text)

            # If LLM extraction was confident, use it directly
            if (llm_result.get("confidence") in ["medium", "high"]
                    and llm_result.get("vendor_name") != "Unknown Vendor"):

                llm_result["raw_text"]   = raw_text
                llm_result["ocr_engine"] = ocr_result.get("engine", "unknown")
                llm_result["status"]     = "success"
                llm_result["project_name"] = "General"

                # ── Normalize category from Gemini ────────────────
                # Import inline to avoid circular imports
                from src.llm_extractor import _validate_category
                llm_result["category"] = _validate_category(
                    llm_result.get("category", "Miscellaneous")
                )

                # Mark extraction method clearly for UI
                llm_result["extraction_method"]   = "llm_gemini"
                llm_result["category_method"]     = "llm_gemini"
                llm_result["category_confidence"] = 0.95

                print(f"   ✅ Using LLM extraction result.")
                return llm_result

        except Exception as e:
            print(f"   ⚠️ LLM failed, falling back to rules: {e}")

    # ── Fallback: original regex-based extraction ─────────────────
    print("   📐 Using rule-based extraction (fallback)...")

    raw_text = ocr_result.get("text", "")

    if not raw_text:
        return {
            "vendor_name": "Unknown Vendor",
            "date": "Unknown Date",
            "total_amount": 0.0,
            "category": "Uncategorized",  # Step 4 will fill this
            "project_name": "General",
            "raw_text": "",
            "ocr_engine": ocr_result.get("engine", "unknown"),
            "status": "failed - no text extracted"
        }

    print("\n🧹 Cleaning and parsing extracted text...")

    # Step 1: Clean the raw text
    clean_text = clean_raw_text(raw_text)

    # Step 2: Extract each field
    vendor   = extract_vendor(clean_text)
    date     = extract_date(clean_text)
    amount   = extract_amount(clean_text)
    project  = extract_project(clean_text)

    # Step 3: Build result
    result = {
        "vendor_name":  vendor,
        "date":         date,
        "total_amount": amount,
        "category":     "Uncategorized",  # AI categorizer fills this next
        "project_name": project,
        "raw_text":     clean_text,
        "ocr_engine":   ocr_result.get("engine", "unknown"),
        "confidence":   ocr_result.get("confidence", 0),
        "status":       "success" if vendor != "Unknown Vendor" else "partial"
    }

    # Step 4: Log what we found
    print(f"   🏪 Vendor  : {result['vendor_name']}")
    print(f"   📅 Date    : {result['date']}")
    print(f"   💰 Amount  : Rs {result['total_amount']:,.2f}")
    print(f"   📁 Project : {result['project_name']}")
    print(f"   📊 Status  : {result['status']}")

    return result
