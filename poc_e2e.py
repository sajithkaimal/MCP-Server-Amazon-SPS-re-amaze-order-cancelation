#!/usr/bin/env python3
"""
POC: Re:amaze (read, optional write) + Amazon SP-API (read-only) sanity check.

- Re:amaze: GET one unresolved conversation; optional POST a private note if REAMAZE_WRITE=1
- Amazon SP-API: Sellers.get_marketplace_participation() to prove LWA + SigV4 signing
  Uses the maintained `python-amazon-sp-api` package (module: sp_api)

Env vars required (minimal POC):
  REAMAZE_BRAND            e.g., "acme"            (host becomes https://acme.reamaze.io)
  REAMAZE_EMAIL            login email that OWNS the API token
  REAMAZE_API_TOKEN        per-user API token

  LWA_CLIENT_ID
  LWA_CLIENT_SECRET
  REFRESH_TOKEN
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  # optional: AWS_SELLER_PARTNER_ROLE_ARN   (must be a ROLE ARN, not a user ARN)

  # optional toggles (defaults shown)
  SPAPI_REGION=NA
  SPAPI_MARKETPLACE=US
  SPAPI_SANDBOX=1
  REAMAZE_WRITE=0
  LIMIT_TO_CONVO=           (specific conversation slug to target)
"""

import os
import json
from typing import Optional

import requests
from dotenv import load_dotenv


# ------------------------- Re:amaze helpers ------------------------- #

def reamaze_base() -> str:
    brand = os.environ["REAMAZE_BRAND"]
    return f"https://{brand}.reamaze.io/api/v1"


def reamaze_auth():
    # Must be: login email (owner of token) + API token
    return (os.environ["REAMAZE_EMAIL"], os.environ["REAMAZE_API_TOKEN"])


def get_one_conversation() -> Optional[dict]:
    base = reamaze_base()
    auth = reamaze_auth()
    brand = os.environ["REAMAZE_BRAND"]
    slug = os.getenv("LIMIT_TO_CONVO", "").strip()

    try:
        if slug:
            r = requests.get(
                f"{base}/conversations/{slug}.json",
                auth=auth,
                timeout=20
            )
            r.raise_for_status()
            return r.json().get("conversation")

        r = requests.get(
            f"{base}/conversations.json",
            auth=auth,
            params={"brand": brand, "state": "unresolved", "per_page": 1},
            timeout=20,
        )
        r.raise_for_status()
        convs = r.json().get("conversations", [])
        return convs[0] if convs else None

    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 403:
            print("[Re:amaze] ❌ 403 Forbidden – check that REAMAZE_EMAIL is the SAME account that generated the token, and REAMAZE_BRAND matches your subdomain.")
        else:
            print(f"[Re:amaze] ❌ HTTP error: {e}")
        return None
    except Exception as e:
        print(f"[Re:amaze] ❌ Error: {e}")
        return None


def add_private_note(slug: str, body: str):
    base = reamaze_base()
    auth = reamaze_auth()
    r = requests.post(
        f"{base}/conversations/{slug}/messages.json",
        auth=auth,
        json={"message": {"body": body, "private": True}},
        timeout=20,
    )
    return r.ok, r.text


# ------------------------- SP-API helpers ------------------------- #

def has_spapi_env() -> bool:
    need = [
        "LWA_CLIENT_ID",
        "LWA_CLIENT_SECRET",
        "REFRESH_TOKEN",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    ]
    return all(os.getenv(k) for k in need)


def spapi_region_marketplace():
    # Region is unused in the python-amazon-sp-api call but kept for completeness
    region = os.getenv("SPAPI_REGION", "NA").upper()
    mp = os.getenv("SPAPI_MARKETPLACE", "US").upper()
    return region, mp


def spapi_sanity_check():
    """
    Prove LWA + AWS signing using Sellers.get_marketplace_participation().
    Works with user keys; role_arn is optional.
    Supports both newer (singular) and older (plural) method names.
    """
    from sp_api.api import Sellers
    from sp_api.base import Marketplaces, SellingApiException

    _, mp = spapi_region_marketplace()
    marketplace = getattr(Marketplaces, mp)

    creds = dict(
        refresh_token=os.environ["REFRESH_TOKEN"],
        lwa_app_id=os.getenv("LWA_CLIENT_ID") or os.getenv("LWA_APP_ID"),
        lwa_client_secret=os.environ["LWA_CLIENT_SECRET"],
        aws_access_key=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_key=os.environ["AWS_SECRET_ACCESS_KEY"],
    )
    role_arn = os.getenv("AWS_SELLER_PARTNER_ROLE_ARN", "").strip()
    if role_arn:
        creds["role_arn"] = role_arn  # must be a ROLE ARN if provided

    sandbox_flag = os.getenv("SPAPI_SANDBOX", "1") == "1"

    # Instantiate Sellers with best-effort sandbox toggle across versions
    sellers = None
    try:
        sellers = Sellers(credentials=creds, marketplace=marketplace, use_sandbox=sandbox_flag)
    except TypeError:
        try:
            sellers = Sellers(credentials=creds, marketplace=marketplace, sandbox=sandbox_flag)
        except TypeError:
            sellers = Sellers(credentials=creds, marketplace=marketplace)

    try:
        try:
            resp = sellers.get_marketplace_participation()   # newer name
        except AttributeError:
            resp = sellers.get_marketplace_participations()  # older name
        return {"ok": True, "payload": resp.payload}
    except SellingApiException as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected: {e}"}


# ------------------------------ Main ------------------------------ #

def main():
    load_dotenv()
    print("=== POC: Re:amaze + Amazon SP-API (read-only by default) ===")

    # ---------- Re:amaze GET ----------
    conv = get_one_conversation()
    if conv:
        slug = conv["slug"]
        subj = conv.get("subject", "")
        print(f"[Re:amaze] ✅ Fetched conversation slug={slug} subject={subj!r}")
        if os.getenv("REAMAZE_WRITE", "0") == "1":
            ok, resp = add_private_note(slug, "[POC] Hello from poc_e2e.py (safe test).")
            print(f"[Re:amaze] POST private note -> ok={ok}")
            if not ok:
                print(resp)
    else:
        print("[Re:amaze] (No conversation fetched.) See messages above if there was an auth error.")

    # ---------- Amazon SP-API Sellers.get_marketplace_participation ----------
    if has_spapi_env():
        res = spapi_sanity_check()
        if res.get("ok"):
            payload = res.get("payload", {})
            parts = payload.get("payload") or payload  # handle different shapes
            print("[SP-API] ✅ get_marketplace_participation(s) succeeded.")
            try:
                print(json.dumps(parts, indent=2)[:2000])
            except Exception:
                print(str(parts)[:2000])
        else:
            print("[SP-API] ❌ Error:", res.get("error"))
    else:
        print("[SP-API] Skipping: missing env vars (need LWA_CLIENT_ID/LWA_CLIENT_SECRET/REFRESH_TOKEN and AWS access key/secret).")


if __name__ == "__main__":
    main()
