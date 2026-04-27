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
    Extract the vendor/store name from receipt text.

    Strategy:
    - Most receipts have the store name at the TOP
    - It's usually in ALL CAPS or Title Case
    - It's usually on one of the first 5 lines
    - Skip lines that look like addresses or phone numbers

    Args:
        text: Cleaned OCR text

    Returns:
        Vendor name string, or "Unknown Vendor"
    """
    lines = text.strip().splitlines()

    # Patterns that indicate a line is NOT a vendor name
    skip_patterns = [
        r'\d{3,}',           # Lines with long numbers (phone, address)
        r'@',                # Email addresses
        r'http',             # URLs
        r'www\.',            # Websites
        r'gst|gstin',        # Tax lines
        r'invoice|bill no',  # Invoice headers
        r'date:|time:',      # Date/time lines
        r'thank you',        # Footer text
        r'^\s*$',            # Empty lines
        r'={3,}|-{3,}',      # Separator lines like === or ---
    ]

    for line in lines[:8]:  # Check only first 8 lines
        line = line.strip()

        # Must be at least 3 characters
        if len(line) < 3:
            continue

        # Check if line matches any skip pattern
        should_skip = any(
            re.search(pattern, line, re.IGNORECASE)
            for pattern in skip_patterns
        )

        if should_skip:
            continue

        # Clean up the vendor name
        vendor = re.sub(r'[^a-zA-Z0-9\s&\'\-]', '', line)
        vendor = vendor.strip()

        if len(vendor) >= 3:
            return vendor.title()  # "QUICK MART" → "Quick Mart"

    return "Unknown Vendor"


# ─────────────────────────────────────────────
# STEP 3: DATE EXTRACTION
# ─────────────────────────────────────────────

def extract_date(text: str) -> str:
    """
    Find and standardize the date from receipt text.

    Handles many formats:
    - 25-Apr-2025
    - 25/04/2025
    - 04/25/2025 (US format)
    - April 25, 2025
    - 25.04.25
    - 2025-04-25 (ISO format)

    Returns:
        Date in standard format: YYYY-MM-DD
        Or "Unknown Date" if not found
    """

    # Map month names/abbreviations → numbers
    month_map = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
        'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
        'january': '01', 'february': '02', 'march': '03',
        'april': '04', 'june': '06', 'july': '07',
        'august': '08', 'september': '09', 'october': '10',
        'november': '11', 'december': '12'
    }

    # Pattern 1: 25-Apr-2025 or 25/Apr/2025
    match = re.search(
        r'(\d{1,2})[-/\s]([a-zA-Z]{3,9})[-/\s](\d{2,4})',
        text, re.IGNORECASE
    )
    if match:
        day, month_str, year = match.groups()
        month = month_map.get(month_str.lower())
        if month:
            year = _fix_year(year)
            return f"{year}-{month}-{day.zfill(2)}"

    # Pattern 2: 25/04/2025 or 25-04-2025 or 25.04.2025
    match = re.search(
        r'(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})',
        text
    )
    if match:
        part1, part2, part3 = match.groups()
        year = _fix_year(part3)
        # Assume DD/MM/YYYY (Indian format)
        return f"{year}-{part2.zfill(2)}-{part1.zfill(2)}"

    # Pattern 3: April 25, 2025 or 25 April 2025
    match = re.search(
        r'([a-zA-Z]{3,9})\s+(\d{1,2}),?\s+(\d{4})',
        text, re.IGNORECASE
    )
    if match:
        month_str, day, year = match.groups()
        month = month_map.get(month_str.lower())
        if month:
            return f"{year}-{month}-{day.zfill(2)}"

    # Pattern 4: ISO format 2025-04-25
    match = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
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
    Extract the TOTAL amount from receipt text.

    Improved strategy:
    1. Search for TOTAL keyword line first (strict)
    2. Prefer TOTAL over Subtotal
    3. Fall back to largest amount only if no keyword found
    """

    total_keywords = [
        "grand total", "total amount", "net payable",
        "total payable", "amount due", "balance due",
        "net amount", "total"          # 'total' last — it's generic
    ]

    # ── Strategy 1: keyword line match (strict) ──────────────────
    lines = text.splitlines()

    for keyword in total_keywords:
        for line in lines:
            line_lower = line.lower().strip()

            # Skip lines that are clearly subtotals
            if any(skip in line_lower for skip in ["subtotal", "sub total", "sub-total"]):
                continue

            similarity = fuzz.partial_ratio(keyword, line_lower)

            if similarity >= 80:
                amount = _extract_number_from_line(line)
                if amount and amount > 1:
                    print(f"   💡 Amount found via keyword '{keyword}' in: {line.strip()}")
                    return amount

    # ── Strategy 2: look for currency symbol near TOTAL word ─────
    # Handles "TOTAL: Rs 1,280" or "TOTAL .......... 1280"
    total_line_pattern = re.search(
        r'total[^\n]{0,30}?(?:Rs\.?|INR|₹|\$)?\s*([\d,]+(?:\.\d{1,2})?)',
        text,
        re.IGNORECASE
    )
    if total_line_pattern:
        try:
            amount = float(total_line_pattern.group(1).replace(',', ''))
            if amount > 1:
                print(f"   💡 Amount found via total pattern: {amount}")
                return amount
        except ValueError:
            pass

    # ── Strategy 3: all currency amounts → return largest ────────
    currency_pattern = r'(?:Rs\.?|INR|₹|\$|€|£)\s*([\d,]+(?:\.\d{1,2})?)'
    all_amounts = re.findall(currency_pattern, text)

    parsed = []
    for amt_str in all_amounts:
        try:
            val = float(amt_str.replace(',', ''))
            if val > 1:
                parsed.append(val)
        except ValueError:
            continue

    if parsed:
        largest = max(parsed)
        print(f"   💡 Amount found via largest number fallback: {largest}")
        return largest

    return 0.0

def _extract_number_from_line(line: str) -> float:
    """Helper: extract the last number from a line of text."""
    # Find all numbers in the line
    numbers = re.findall(r'[\d,]+(?:\.\d{1,2})?', line)
    if numbers:
        try:
            # Take the last number (usually the amount, not a quantity)
            return float(numbers[-1].replace(',', ''))
        except ValueError:
            return 0.0
    return 0.0


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

def parse_receipt(ocr_result: dict) -> dict:
    """
    Master function: takes OCR result, returns structured data.

    Args:
        ocr_result: Dictionary from ocr_engine.extract_text()
                    Must have 'text' key

    Returns:
        Structured dictionary with all extracted fields
    """
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