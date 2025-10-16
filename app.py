#!/usr/bin/env python3
"""
Orchestrator: pulls one unresolved Re:amaze ticket, classifies with Claude,
(optionally) cancels in Amazon SP-API, and writes a private note + tags.

Safe by default: DRY_RUN=true in rules.yaml prevents real cancellations.
"""

import os
import json
from dotenv import load_dotenv

from reamaze import (
    get_one_conversation,
    add_private_note,
    add_tags,
    assign_to,
)
from classify import classify_ticket
from amazon import cancel_mcf_fulfillment, build_cancel_payload
from storage import init_db, log_action, db_path
from utils import load_rules, normalize_shopify_order_id


def main():
    load_dotenv()
    rules = load_rules()
    init_db()

    print("=== cancelbot: Re:amaze + Claude + SP-API ===")
    dry_run = bool(rules.get("dry_run", True))

    convo = get_one_conversation()
    if not convo:
        print("[Re:amaze] No unresolved conversations found or auth error.")
        return

    slug = convo["slug"]
    subject = convo.get("subject", "")
    last_msg_text = ""
    if convo.get("messages"):
        m = convo["messages"][-1]
        last_msg_text = m.get("body_text") or m.get("plain_body") or ""

    combined = f"{subject}\n\n{last_msg_text}".strip() or subject

    # ---- classify with Claude ----
    cls = classify_ticket(combined)
    print("[Claude] classification:", json.dumps(cls, indent=2))

    intent = cls.get("intent", "not_cancellation")
    order_id = cls.get("order_id")
    if order_id:
        order_id = normalize_shopify_order_id(order_id)

    if intent != "cancel_order":
        note = (
            "[POC] Not a cancellation based on classifier.\n\n"
            f"Classifier JSON:\n```json\n{json.dumps(cls, indent=2)}\n```"
        )
        ok, resp = add_private_note(slug, note)
        add_tags(slug, rules["tags"].get("not_cancellation", []))
        assign_to(slug, rules.get("assignee"))
        log_action(slug, order_id, "not_cancellation", ok, {"classifier": cls})
        print(f"[Re:amaze] Noted classification; tags added; assigned to {rules.get('assignee')}. DB:", db_path())
        return

    # intent == cancel_order
    if not order_id:
        note = (
            "[POC] Cancellation intent detected but no order id found.\n"
            "Tagged needs-human and assigned."
        )
        ok, resp = add_private_note(slug, note)
        add_tags(slug, rules["tags"].get("failure", []))
        assign_to(slug, rules.get("assignee"))
        log_action(slug, None, "cancel_order", False, {"error": "missing_order_id", "classifier": cls})
        print(f"[Re:amaze] Missing order id → needs-human. DB:", db_path())
        return

    # Build payload (shown even in dry-run)
    payload = build_cancel_payload(order_id)

    if dry_run:
        note = (
            "✅ [POC/DRY RUN] Classified as cancellation.\n"
            "No Amazon call made. Here is the payload that WOULD be sent:\n\n"
            f"```json\n{json.dumps(payload, indent=2)}\n```\n"
            f"Classifier: {json.dumps(cls, indent=2)}"
        )
        ok, resp = add_private_note(slug, note)
        add_tags(slug, rules["tags"].get("success", []))
        assign_to(slug, rules.get("assignee"))
        log_action(slug, order_id, "cancel_order", True, {"dry_run": True, "payload": payload, "classifier": cls})
        print("[DRY RUN] Note posted; tags added; assigned; logged.")
        return

    # Real call (only if dry_run == False)
    result = cancel_mcf_fulfillment(order_id)
    if result["ok"]:
        note = (
            f"✅ Auto-cancel success via SP-API for `{order_id}`.\n\n"
            f"Response:\n```json\n{json.dumps(result['payload'], indent=2)}\n```"
        )
        add_private_note(slug, note)
        add_tags(slug, rules["tags"].get("success", []))
        success = True
    else:
        note = (
            f"⚠️ Auto-cancel failed for `{order_id}`.\n\n"
            f"Error:\n```\n{result['error']}\n```\nTagged needs-human."
        )
        add_private_note(slug, note)
        add_tags(slug, rules["tags"].get("failure", []))
        success = False

    assign_to(slug, rules.get("assignee"))
    log_action(slug, order_id, "cancel_order", success, result)
    print(f"[SP-API] {'Success' if success else 'Failure'}; ticket updated; DB:", db_path())


if __name__ == "__main__":
    main()
