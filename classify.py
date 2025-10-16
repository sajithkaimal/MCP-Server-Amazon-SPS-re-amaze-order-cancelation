"""
Claude classifier with robust JSON parsing (no response_format arg required).

- Uses ANTHROPIC_MODEL if set; else tries a short fallback list you can edit.
- Forces JSON via instruction and validates/repairs output if needed.
- Never crashes; returns a safe default on error.
"""

import os, json, re
from typing import Dict, Any, List

from anthropic import Anthropic, NotFoundError  # pip install -U anthropic

SYSTEM = """You are a precise CX triage helper.
Respond with ONLY a single JSON object (no prose, no code fences), with keys:
- intent: "cancel_order" | "not_cancellation"
- order_id: string or null  (if numeric like 91057, that's fine; do not invent)
- is_subscription_related: boolean
- urgency: "low" | "normal" | "high"
- rationale: short string
"""

# Use the models your key actually lists (adjust as you like)
FALLBACK_MODELS: List[str] = [
    os.getenv("ANTHROPIC_MODEL", "").strip() or "",
    "claude-sonnet-4-20250514",
    "claude-3-7-sonnet-20250219",
    "claude-3-5-haiku-20241022",
    "claude-3-haiku-20240307",
]
FALLBACK_MODELS = [m for m in FALLBACK_MODELS if m]

_DEF = {
    "intent": "not_cancellation",
    "order_id": None,
    "is_subscription_related": False,
    "urgency": "normal",
    "rationale": "Classifier fallback.",
}

def _extract_text(resp) -> str:
    """Concatenate text blocks safely (Anthropic returns a list of content blocks)."""
    parts = []
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts).strip()

def _coerce_json(txt: str) -> Dict[str, Any]:
    """
    Try strict JSON first; if it fails, strip code fences or grab the first {...} blob.
    Always return a dict or raise.
    """
    try:
        return json.loads(txt)
    except Exception:
        pass
    # Strip common ```json ... ``` wrappers
    m = re.search(r"\{.*\}", txt, flags=re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError("No valid JSON object found.")

def classify_ticket(message_text: str) -> Dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        out = dict(_DEF); out["rationale"] = "No ANTHROPIC_API_KEY set."
        return out

    client = Anthropic(api_key=api_key)
    last_err = None

    for model in FALLBACK_MODELS:
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=400,
                temperature=0,
                system=SYSTEM,
                messages=[{"role": "user", "content": message_text}],
            )
            txt = _extract_text(resp)
            if not txt:
                raise ValueError("Empty text returned from model.")
            data = _coerce_json(txt)

            # Minimal normalization
            data.setdefault("intent", "not_cancellation")
            data.setdefault("order_id", None)
            data.setdefault("is_subscription_related", False)
            data.setdefault("urgency", "normal")
            data.setdefault("rationale", "")
            return data

        except NotFoundError as e:
            last_err = f"Model not found: {model} ({e})"
            continue
        except Exception as e:
            last_err = f"Anthropic error on {model}: {e}"
            # try next model
            continue

    out = dict(_DEF)
    if last_err:
        out["rationale"] = f"Classifier fallback: {last_err}"
    return out
