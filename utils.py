# utils.py
import os
import yaml
import re

def load_rules() -> dict:
    path = os.path.join(os.getcwd(), "rules.yaml")
    if not os.path.exists(path):
        return {"assignee": None, "tags": {"success": [], "failure": [], "not_cancellation": []}, "dry_run": True}
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}

def normalize_shopify_order_id(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    # Try to coerce "91057" -> "Shopify #91057.1"
    digits = re.sub(r"[^\d]", "", s)
    if digits and (digits == s or s.lower().startswith("order") or s.lower().startswith("shopify")):
        return f"Shopify #{digits}.1"
    # Already "Shopify #12345" -> ensure ".1"
    if s.lower().startswith("shopify #") and ".1" not in s:
        return s + ".1"
    return s
