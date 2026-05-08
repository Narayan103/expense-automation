"""
erpnext_exporter.py
-------------------
Pushes processed receipt data into ERPNext
as Expense Claims — automatically.

ERPNext Expense Claim flow:
  Draft → Submitted → Approved → Paid
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

ERPNEXT_URL    = os.getenv("ERPNEXT_URL", "")
ERPNEXT_API_KEY    = os.getenv("ERPNEXT_API_KEY", "")
ERPNEXT_API_SECRET = os.getenv("ERPNEXT_API_SECRET", "")


# ─────────────────────────────────────────────
# AUTHENTICATION
# ─────────────────────────────────────────────

def get_headers() -> dict:
    """
    ERPNext uses token-based authentication.
    Format: "token api_key:api_secret"
    """
    return {
        "Authorization": f"token {ERPNEXT_API_KEY}:{ERPNEXT_API_SECRET}",
        "Content-Type" : "application/json",
        "Accept"       : "application/json"
    }


def test_connection() -> bool:
    """Test if ERPNext connection works."""
    try:
        response = requests.get(
            f"{ERPNEXT_URL}/api/method/frappe.auth.get_logged_user",
            headers=get_headers(),
            timeout=10
        )
        if response.status_code == 200:
            user = response.json().get("message")
            print(f"✅ ERPNext connected as: {user}")
            return True
        else:
            print(f"❌ ERPNext connection failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ ERPNext connection error: {e}")
        return False


# ─────────────────────────────────────────────
# EXPENSE CLAIM CREATION
# ─────────────────────────────────────────────

def create_expense_claim(receipt: dict, employee_id: str = "EMP-0001") -> dict:
    """
    Create an Expense Claim in ERPNext from receipt data.

    ERPNext Expense Claim structure:
    - employee: who submitted
    - expense_date: when was the expense
    - expenses: list of line items
    - total_claimed_amount: total

    Args:
        receipt: Fully processed receipt dict from our pipeline
        employee_id: ERPNext employee ID

    Returns:
        Created expense claim details
    """
    print(f"\n📤 Creating ERPNext Expense Claim...")

    # Map our category to ERPNext expense type
    expense_type = _map_category_to_erpnext(
        receipt.get("category", "Miscellaneous")
    )

    # Build ERPNext expense claim payload
    payload = {
        "doctype"              : "Expense Claim",
        "employee"             : employee_id,
        "expense_approver"     : "",          # Auto-assign based on ERPNext rules
        "posting_date"         : receipt.get("date", ""),
        "company"              : _get_default_company(),
        "expenses": [
            {
                "doctype"         : "Expense Claim Detail",
                "expense_date"    : receipt.get("date", ""),
                "expense_type"    : expense_type,
                "description"     : f"{receipt.get('vendor_name')} — auto-extracted by AI",
                "amount"          : receipt.get("total_amount", 0),
                "sanctioned_amount": receipt.get("total_amount", 0),
            }
        ],
        "total_claimed_amount" : receipt.get("total_amount", 0),
        "total_sanctioned_amount": receipt.get("total_amount", 0),
        "remark"               : _build_remark(receipt),
    }

    try:
        response = requests.post(
            f"{ERPNEXT_URL}/api/resource/Expense Claim",
            headers=get_headers(),
            json=payload,
            timeout=15
        )

        if response.status_code in [200, 201]:
            data     = response.json()
            doc_name = data.get("data", {}).get("name", "")

            print(f"✅ Expense Claim created: {doc_name}")
            print(f"   Vendor  : {receipt.get('vendor_name')}")
            print(f"   Amount  : Rs {receipt.get('total_amount')}")
            print(f"   Type    : {expense_type}")

            return {
                "success"          : True,
                "expense_claim_id" : doc_name,
                "url"              : f"{ERPNEXT_URL}/app/expense-claim/{doc_name}",
                "status"           : "Draft"
            }
        else:
            error = response.json().get("message", response.text)
            print(f"❌ Failed to create claim: {error}")
            return {"success": False, "error": error}

    except Exception as e:
        print(f"❌ ERPNext API error: {e}")
        return {"success": False, "error": str(e)}


# ─────────────────────────────────────────────
# HELPER FUNCTIONS
# ─────────────────────────────────────────────

def _map_category_to_erpnext(category: str) -> str:
    """
    Map our AI categories to ERPNext Expense Types.
    ERPNext has predefined expense types — we map ours to them.
    """
    mapping = {
        "Office Supplies"         : "Office Supplies",
        "Travel & Transport"      : "Travel",
        "Meals & Entertainment"   : "Entertainment",
        "Software & Subscriptions": "Software",
        "Accommodation"           : "Accommodation",
        "Medical & Health"        : "Medical",
        "Communication"           : "Telephone & Internet",
        "Equipment & Hardware"    : "Hardware",
        "Training & Education"    : "Training",
        "Fuel & Petrol"           : "Fuel",
        "Newspaper & Media"       : "Newspaper",
        "Shopping & Retail"       : "Miscellaneous",
        "Utilities & Services"    : "Utility",
        "Miscellaneous"           : "Miscellaneous",
    }
    return mapping.get(category, "Miscellaneous")


def _get_default_company() -> str:
    """Get the default company from ERPNext."""
    try:
        response = requests.get(
            f"{ERPNEXT_URL}/api/resource/Company?limit=1",
            headers=get_headers(),
            timeout=10
        )
        if response.status_code == 200:
            companies = response.json().get("data", [])
            if companies:
                return companies[0].get("name", "")
    except Exception:
        pass
    return ""


def _build_remark(receipt: dict) -> str:
    """Build a descriptive remark for the expense claim."""
    lines = [
        f"Vendor: {receipt.get('vendor_name', 'Unknown')}",
        f"Date: {receipt.get('date', 'Unknown')}",
        f"Category: {receipt.get('category', 'Unknown')}",
        f"OCR Engine: {receipt.get('ocr_engine', 'Unknown')}",
        f"Extraction: {receipt.get('extraction_method', 'rules')}",
        f"Bank Match: {receipt.get('reconciliation_status', 'not_run')}",
        f"Auto-processed by AI Expense System"
    ]
    return " | ".join(lines)


# ─────────────────────────────────────────────
# BATCH EXPORT
# ─────────────────────────────────────────────

def export_batch_to_erpnext(receipts: list, employee_id: str) -> dict:
    """
    Export multiple receipts to ERPNext.

    Returns:
        Summary of success/failure counts
    """
    print(f"\n📦 Batch exporting {len(receipts)} receipts to ERPNext...")

    success = 0
    failed  = 0
    claims  = []

    for i, receipt in enumerate(receipts, 1):
        print(f"\n[{i}/{len(receipts)}]", end=" ")
        result = create_expense_claim(receipt, employee_id)

        if result.get("success"):
            success += 1
            claims.append(result.get("expense_claim_id"))
        else:
            failed += 1

    print(f"\n{'='*40}")
    print(f"📊 ERPNEXT EXPORT SUMMARY")
    print(f"  ✅ Success : {success}")
    print(f"  ❌ Failed  : {failed}")
    print(f"  📋 Claims  : {claims}")

    return {
        "success": success,
        "failed" : failed,
        "claims" : claims
    }