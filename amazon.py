"""
Amazon SP-API helpers (Fulfillment Outbound). Uses python-amazon-sp-api.

Safe by default: app.py controls DRY_RUN; this module exposes:
- build_cancel_payload(order_id)  -> dict
- cancel_mcf_fulfillment(order_id) -> {ok: bool, payload|error}
"""

import os
from typing import Dict

def _creds() -> Dict[str, str]:
    # Role is optional; if provided, it MUST be a ROLE ARN (not a user ARN).
    creds = dict(
        refresh_token=os.environ["REFRESH_TOKEN"],
        lwa_app_id=os.getenv("LWA_CLIENT_ID") or os.getenv("LWA_APP_ID"),
        lwa_client_secret=os.environ["LWA_CLIENT_SECRET"],
        aws_access_key=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )
    role_arn = os.getenv("AWS_SELLER_PARTNER_ROLE_ARN", "").strip()
    if role_arn:
        creds["role_arn"] = role_arn
    return creds


def build_cancel_payload(order_id: str) -> Dict:
    return {
        "operation": "cancel_fulfillment_order",
        "sellerFulfillmentOrderId": order_id,
        "reasonCode": "CustomerRequest",
        "comment": "Automated cancellation request",
    }


def cancel_mcf_fulfillment(order_id: str) -> Dict:
    """
    Calls SP-API Fulfillment Outbound cancel_fulfillment_order.
    Tries multiple method signatures to support different library versions.
    """
    try:
        # Prefer current class name; fall back to older one if needed
        from sp_api.api import FulfillmentOutbound as _FO
        from sp_api.base import Marketplaces, SellingApiException
        fo_cls = _FO
    except Exception:
        try:
            from sp_api.api import FbaOutbound as _FO  # older name
            from sp_api.base import Marketplaces, SellingApiException
            fo_cls = _FO
        except Exception as e:
            return {"ok": False, "error": f"SP-API client import failed: {e}"}

    creds = _creds()
    use_sandbox = os.getenv("SPAPI_SANDBOX", "1") == "1"

    # Instantiate client (handle param name differences across versions)
    try:
        fo = fo_cls(credentials=creds, marketplace=Marketplaces.US, use_sandbox=use_sandbox)
    except TypeError:
        try:
            fo = fo_cls(credentials=creds, marketplace=Marketplaces.US, sandbox=use_sandbox)
        except TypeError:
            fo = fo_cls(credentials=creds, marketplace=Marketplaces.US)

    try:
        # 1) Newer snake_case
        try:
            resp = fo.cancel_fulfillment_order(seller_fulfillment_order_id=order_id)
        except TypeError:
            # 2) camelCase (what your error message shows)
            try:
                resp = fo.cancel_fulfillment_order(sellerFulfillmentOrderId=order_id)
            except TypeError:
                # 3) positional only (some older builds)
                resp = fo.cancel_fulfillment_order(order_id)

        payload = getattr(resp, "payload", resp)
        return {"ok": True, "payload": payload}

    except SellingApiException as e:
        return {"ok": False, "error": str(e)}
    except TypeError as e:
        # Still a signature issue
        return {"ok": False, "error": f"Signature mismatch: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected: {e}"}
