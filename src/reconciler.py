"""
reconciler.py
-------------
Matches receipt data against bank statement entries.

Matching logic:
  1. Amount must match exactly (or within 1%)
  2. Date must be within 3 days
  3. Vendor name must be 50%+ similar (fuzzy)

Outputs a match result with confidence score.
"""

import pandas as pd
from datetime import datetime, timedelta
from rapidfuzz import fuzz
import os


# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────

# How strict should matching be?
AMOUNT_TOLERANCE_PERCENT = 1.0   # Allow 1% difference in amount
DATE_TOLERANCE_DAYS      = 3     # Allow 3 days difference
NAME_SIMILARITY_MIN      = 50    # Minimum fuzzy name match %


# ─────────────────────────────────────────────
# STEP 1: LOAD BANK STATEMENT
# ─────────────────────────────────────────────

def load_bank_statement(csv_path: str) -> pd.DataFrame:
    """
    Load and standardize a bank statement CSV file.

    Handles common variations:
    - Different column names (Description vs Narration vs Details)
    - Different date formats
    - Amount as string with commas

    Args:
        csv_path: Path to the CSV file

    Returns:
        Cleaned pandas DataFrame
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Bank statement not found: {csv_path}")

    print(f"\n📂 Loading bank statement: {csv_path}")
    df = pd.read_csv(csv_path)

    print(f"   Found {len(df)} transactions")
    print(f"   Columns: {list(df.columns)}")

    # ── Standardize column names ──────────────────────────────────
    # Different banks use different names — we normalize them
    column_map = {
        # Date columns
        "date"            : "date",
        "transaction date": "date",
        "txn date"        : "date",
        "value date"      : "date",

        # Description columns
        "description"     : "description",
        "narration"       : "description",
        "particulars"     : "description",
        "details"         : "description",
        "remarks"         : "description",

        # Amount columns
        "amount"          : "amount",
        "debit"           : "amount",
        "transaction amount": "amount",
        "withdrawal"      : "amount",
    }

    df.columns = [col.lower().strip() for col in df.columns]
    df = df.rename(columns=column_map)

    # ── Ensure required columns exist ────────────────────────────
    required = ["date", "description", "amount"]
    for col in required:
        if col not in df.columns:
            raise ValueError(
                f"Column '{col}' not found in bank statement.\n"
                f"Available columns: {list(df.columns)}"
            )

    # ── Clean amount column ───────────────────────────────────────
    df["amount"] = (
        df["amount"]
        .astype(str)
        .str.replace(",", "")        # Remove commas: 1,280 → 1280
        .str.replace("Rs", "")       # Remove currency symbols
        .str.replace("₹", "")
        .str.strip()
    )
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

    # ── Parse dates ───────────────────────────────────────────────
    df["date_parsed"] = pd.to_datetime(
        df["date"],
        dayfirst=True,               # Indian format: DD/MM/YYYY
        errors="coerce"
    )

    # ── Clean description ─────────────────────────────────────────
    df["description"] = df["description"].astype(str).str.upper().str.strip()

    # Keep only debit transactions (expenses)
    if "type" in df.columns:
        df = df[df["type"].str.lower() == "debit"].copy()
        print(f"   Debit transactions: {len(df)}")

    print(f"   ✅ Bank statement loaded successfully.")
    return df


# ─────────────────────────────────────────────
# STEP 2: MATCHING LOGIC
# ─────────────────────────────────────────────

def _amount_matches(receipt_amount: float, bank_amount: float) -> tuple[bool, float]:
    """
    Check if two amounts are close enough to be the same transaction.

    Returns:
        (is_match, difference_percent)
    """
    if bank_amount == 0:
        return False, 100.0

    diff_percent = abs(receipt_amount - bank_amount) / bank_amount * 100
    return diff_percent <= AMOUNT_TOLERANCE_PERCENT, round(diff_percent, 2)


def _date_matches(receipt_date: str, bank_date) -> tuple[bool, int]:
    """
    Check if two dates are within tolerance.

    Returns:
        (is_match, days_difference)
    """
    if pd.isna(bank_date):
        return False, 999

    try:
        r_date = datetime.strptime(receipt_date, "%Y-%m-%d")
        b_date = pd.Timestamp(bank_date).to_pydatetime()
        diff_days = abs((r_date - b_date).days)
        return diff_days <= DATE_TOLERANCE_DAYS, diff_days
    except Exception:
        return False, 999


def _name_matches(vendor: str, bank_desc: str) -> tuple[bool, int]:
    """
    Fuzzy match vendor name against bank description.

    Banks often shorten or uppercase names:
    "Starbucks Coffee" → "STARBUCKS 00234 DELHI"

    Returns:
        (is_match, similarity_score_0_to_100)
    """
    vendor_clean = vendor.upper().strip()
    bank_clean   = bank_desc.upper().strip()

    # Try multiple fuzzy methods, take the best score
    scores = [
        fuzz.partial_ratio(vendor_clean, bank_clean),
        fuzz.token_sort_ratio(vendor_clean, bank_clean),
        fuzz.token_set_ratio(vendor_clean, bank_clean),
    ]
    best_score = max(scores)
    return best_score >= NAME_SIMILARITY_MIN, best_score


def _calculate_match_confidence(
    amount_match: bool,
    date_match: bool,
    name_match: bool,
    name_score: int,
    days_diff: int,
    amount_diff: float
) -> float:
    """
    Calculate overall match confidence (0.0 to 1.0).

    Weighting:
    - Amount match: 50% weight (most reliable signal)
    - Date match:   30% weight
    - Name match:   20% weight
    """
    score = 0.0

    # Amount (50% weight)
    if amount_match:
        score += 0.50 * (1 - amount_diff / 100)

    # Date (30% weight)
    if date_match:
        date_score = 1 - (days_diff / (DATE_TOLERANCE_DAYS + 1))
        score += 0.30 * date_score

    # Name (20% weight)
    if name_match:
        score += 0.20 * (name_score / 100)

    return round(score, 3)


# ─────────────────────────────────────────────
# STEP 3: MAIN RECONCILIATION
# ─────────────────────────────────────────────

def reconcile(parsed_receipt: dict, bank_df: pd.DataFrame) -> dict:
    """
    Try to find a matching bank transaction for a receipt.

    Args:
        parsed_receipt: Dict from text_cleaner + categorizer
        bank_df: DataFrame from load_bank_statement()

    Returns:
        parsed_receipt with reconciliation fields added
    """
    vendor  = parsed_receipt.get("vendor_name", "")
    date    = parsed_receipt.get("date", "")
    amount  = parsed_receipt.get("total_amount", 0)

    print(f"\n🔍 Reconciling: {vendor} | {date} | Rs {amount}")

    best_match     = None
    best_confidence = 0.0
    all_candidates = []

    for _, row in bank_df.iterrows():
        bank_amount = float(row["amount"])
        bank_date   = row["date_parsed"]
        bank_desc   = str(row["description"])

        # Run all three checks
        amt_ok, amt_diff   = _amount_matches(amount, bank_amount)
        date_ok, days_diff = _date_matches(date, bank_date)
        name_ok, name_score = _name_matches(vendor, bank_desc)

        # Must at least match on amount to be a candidate
        if not amt_ok:
            continue

        # Calculate confidence
        confidence = _calculate_match_confidence(
            amt_ok, date_ok, name_ok,
            name_score, days_diff, amt_diff
        )

        candidate = {
            "bank_description" : bank_desc,
            "bank_amount"      : bank_amount,
            "bank_date"        : str(row["date"]),
            "transaction_id"   : row.get("transaction_id", "N/A"),
            "confidence"       : confidence,
            "name_score"       : name_score,
            "days_difference"  : days_diff,
            "amount_diff_pct"  : amt_diff,
        }
        all_candidates.append(candidate)

        if confidence > best_confidence:
            best_confidence = confidence
            best_match = candidate

    # ── Determine match status ────────────────────────────────────
    if best_match and best_confidence >= 0.5:
        status = "matched"
        print(f"   ✅ MATCHED → {best_match['bank_description']}")
        print(f"      Confidence : {best_confidence:.0%}")
        print(f"      Name score : {best_match['name_score']}%")
        print(f"      Days diff  : {best_match['days_difference']}")

    elif best_match and best_confidence >= 0.3:
        status = "possible_match"
        print(f"   ⚠️  POSSIBLE MATCH → {best_match['bank_description']}")
        print(f"      Confidence : {best_confidence:.0%} (needs review)")

    else:
        status = "unmatched"
        best_match = {}
        print(f"   ❌ NO MATCH FOUND — may need manual review")

    # ── Add reconciliation data to receipt ────────────────────────
    parsed_receipt["reconciliation_status"]     = status
    parsed_receipt["matched_bank_description"]  = best_match.get("bank_description", "")
    parsed_receipt["matched_bank_amount"]       = best_match.get("bank_amount", "")
    parsed_receipt["matched_transaction_id"]    = best_match.get("transaction_id", "")
    parsed_receipt["match_confidence"]          = best_confidence
    parsed_receipt["candidates_found"]          = len(all_candidates)

    return parsed_receipt


# ─────────────────────────────────────────────
# BATCH RECONCILIATION
# ─────────────────────────────────────────────

def reconcile_batch(receipts: list, bank_csv_path: str) -> list:
    """
    Reconcile multiple receipts against one bank statement.

    Args:
        receipts: List of parsed receipt dicts
        bank_csv_path: Path to bank statement CSV

    Returns:
        List of receipts with reconciliation data added
    """
    bank_df = load_bank_statement(bank_csv_path)
    results = []

    print(f"\n📋 Reconciling {len(receipts)} receipt(s)...")

    for i, receipt in enumerate(receipts, 1):
        print(f"\n[{i}/{len(receipts)}]", end="")
        reconciled = reconcile(receipt, bank_df)
        results.append(reconciled)

    # Summary
    matched   = sum(1 for r in results if r["reconciliation_status"] == "matched")
    possible  = sum(1 for r in results if r["reconciliation_status"] == "possible_match")
    unmatched = sum(1 for r in results if r["reconciliation_status"] == "unmatched")

    print(f"\n{'='*50}")
    print(f"📊 RECONCILIATION SUMMARY")
    print(f"{'='*50}")
    print(f"  ✅ Matched        : {matched}")
    print(f"  ⚠️  Possible match : {possible}")
    print(f"  ❌ Unmatched      : {unmatched}")
    print(f"  📋 Total          : {len(results)}")

    return results

