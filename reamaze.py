"""
Re:amaze helpers. Auth is HTTP Basic with (login_email, api_token).
"""

import os
from typing import Optional, List, Tuple, Dict, Any
import requests


def _base() -> str:
    brand = os.environ["REAMAZE_BRAND"]
    return f"https://{brand}.reamaze.io/api/v1"


def _auth() -> Tuple[str, str]:
    return (os.environ["REAMAZE_EMAIL"], os.environ["REAMAZE_API_TOKEN"])


def get_one_conversation() -> Optional[Dict[str, Any]]:
    base = _base()
    auth = _auth()
    brand = os.environ["REAMAZE_BRAND"]
    slug = os.getenv("LIMIT_TO_CONVO", "").strip()

    if slug:
        r = requests.get(f"{base}/conversations/{slug}.json", auth=auth, timeout=20)
        if r.ok:
            return r.json().get("conversation")
        print("[Re:amaze] Could not fetch slug:", slug, r.text)
        return None

    r = requests.get(
        f"{base}/conversations.json",
        auth=auth,
        params={"brand": brand, "state": "unresolved", "per_page": 1},
        timeout=20,
    )
    try:
        r.raise_for_status()
    except requests.HTTPError as e:
        if r.status_code == 403:
            print("[Re:amaze] 403 Forbidden – ensure REAMAZE_EMAIL is the SAME account that generated the token, and REAMAZE_BRAND matches the subdomain.")
        else:
            print(f"[Re:amaze] HTTP {r.status_code}: {r.text}")
        return None

    convs = r.json().get("conversations", [])
    return convs[0] if convs else None


def add_private_note(slug: str, body: str) -> Tuple[bool, str]:
    r = requests.post(
        f"{_base()}/conversations/{slug}/messages.json",
        auth=_auth(),
        json={"message": {"body": body, "private": True}},
        timeout=20,
    )
    return r.ok, r.text


def add_tags(slug: str, tags: List[str]) -> Tuple[bool, str]:
    if not tags:
        return True, "no-op"
    r = requests.post(
        f"{_base()}/conversations/{slug}/tags.json",
        auth=_auth(),
        json={"tags": tags},
        timeout=20,
    )
    return r.ok, r.text


def assign_to(slug: str, staff_name: Optional[str]) -> Tuple[bool, str]:
    if not staff_name:
        return True, "no-op"
    r = requests.put(
        f"{_base()}/conversations/{slug}.json",
        auth=_auth(),
        json={"conversation": {"assignee_name": staff_name}},
        timeout=20,
    )
    return r.ok, r.text
