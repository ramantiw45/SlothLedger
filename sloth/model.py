"""The model lanes, and the deterministic floor under them.

One shared shape is returned by every lane:

    {"minutes": int, "verdict": "automate"|"delegate"|"ignore",
     "reason": str, "automation": str|None, "evidence": str, "lane": str}

The model reads intent. It is never allowed to produce the number that ends
up in the ledger: when the description carries a countable quantity, the
count and the per-item rate decide the minutes. That rule is the whole
reason a ledger that calls a hosted model can still be trusted with a figure.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from . import config

MINUTES_FLOOR = 1
MINUTES_CEILING = 480
DEFAULT_MINUTES = 12

# Seconds of human effort per item, by the noun people actually type.
PER_ITEM_SECONDS: dict[str, int] = {
    "receipt": 20,
    "invoice": 20,
    "bill": 25,
    "statement": 30,
    "file": 8,
    "photo": 8,
    "screenshot": 6,
    "email": 25,
    "message": 20,
    "chat": 20,
    "comment": 15,
    "expense": 30,
    "entry": 30,
    "row": 20,
    "line": 15,
    "contact": 15,
    "pdf": 20,
    "spreadsheet": 25,
    "form": 40,
    "post": 60,
    "track": 30,
    "document": 20,
}

AUTOMATION_NAMES = {
    "receipt": "Receipt sorter",
    "invoice": "Invoice filer",
    "bill": "Bill reconciler",
    "statement": "Statement matcher",
    "file": "File sorter",
    "photo": "Photo deduper",
    "screenshot": "Screenshot sorter",
    "email": "Inbox tidier",
    "message": "Message digester",
    "chat": "Chat digester",
    "comment": "Comment triager",
    "expense": "Expense logger",
    "entry": "Entry runner",
    "row": "Row runner",
    "line": "Line runner",
    "contact": "Contact fixer",
    "pdf": "PDF indexer",
    "spreadsheet": "Sheet updater",
    "form": "Form filler",
    "post": "Post drafter",
    "track": "Playlist builder",
    "document": "Document filer",
}

RECURRENCE = re.compile(r"\b(every|each|daily|nightly|weekly|monthly|always|again)\b")
MICRO = re.compile(
    r"\b(replied|answered|watered|forwarded|closed|clicked|sent|sign(ed)?|paid|"
    r"renewed|downloaded|uploaded|booked)\b"
)
HUMAN = re.compile(
    r"\b(call|email|ask|negotiate|complain|chase|remind|apolog\w*|landlord|"
    r"boss|client|customer|bank|doctor|school)\b"
)
COUNT = re.compile(r"\b(\d{1,4})\s*(?:\w+\s+){0,2}?([a-z]+)")


def _clamp(value: float) -> int:
    return int(max(MINUTES_FLOOR, min(MINUTES_CEILING, round(value))))


def _counted(description: str) -> tuple[int, str, int] | None:
    """Return (count, noun, seconds-per-item) when the text states a quantity."""
    text = description.lower()
    words = set(re.findall(r"[a-z]+", text))
    for noun, seconds in PER_ITEM_SECONDS.items():
        if noun not in words and f"{noun}s" not in words and f"{noun}es" not in words:
            continue
        match = COUNT.search(text)
        if not match:
            continue
        count = int(match.group(1))
        if 0 < count <= 5000:
            return count, noun, seconds
    return None


def rules_estimate(description: str) -> dict:
    """The floor: no network, no model, no key. Always answers."""
    text = description.lower()
    counted = _counted(description)
    if counted:
        count, noun, seconds = counted
        minutes = _clamp(count * seconds / 60)
        evidence = f"{count} x {seconds}s = {minutes} min"
    elif MICRO.search(text):
        minutes = 2
        evidence = "one small action, floor estimate"
    else:
        minutes = DEFAULT_MINUTES
        evidence = "no countable quantity, default estimate"

    automation = AUTOMATION_NAMES.get(counted[1]) if counted else None

    if minutes < 3:
        verdict = "ignore"
        reason = "Under three minutes, so the setup would cost more than the chore."
    elif RECURRENCE.search(text):
        verdict = "automate"
        reason = "It comes back, and repeated effort is the expensive part."
    elif HUMAN.search(text) and not counted:
        verdict = "delegate"
        reason = "It needs a person on the other end, not a script."
    elif minutes >= 10:
        verdict = "automate"
        reason = "Mechanical, predictable, and long enough to be worth wiring up."
    else:
        verdict = "ignore"
        reason = "Short and irregular, so it is not worth automating yet."

    if verdict != "automate":
        automation = None

    return {
        "minutes": minutes,
        "verdict": verdict,
        "reason": reason,
        "automation": automation or ("Chore runner" if verdict == "automate" else None),
        "evidence": evidence,
        "lane": "rules",
    }


SYSTEM_PROMPT = """You judge chores for a laziness ledger.

Reply with JSON only, no prose, no code fences:
{"minutes": <int>, "verdict": "automate"|"delegate"|"ignore", "reason": "<max 18 words>", "automation": "<short tool name>"|null}

Rules:
- minutes is how long the chore costs a person when done by hand, 1 to 480.
- automate: mechanical, predictable, or it repeats.
- delegate: it needs another human (a call, a favour, a negotiation).
- ignore: under three minutes, or so rare that automating it is theatre.
- automation is the name of a small tool that would do it, or null when ignoring."""


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\n?|\n?```$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("reply is not an object")
    return data


def _post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 90) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    # Some gateways front their API with a WAF that rejects the stdlib's
    # default User-Agent outright. Identifying the client fixes it.
    request.add_header("User-Agent", "sloth-ledger/0.1")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _ask_compatible(description: str, stated: int | None) -> dict:
    base = (config.setting("MODEL_BASE_URL") or "").rstrip("/")
    key = config.setting("MODEL_API_KEY") or config.setting("GROQ_API_KEY", "")
    model = config.setting("MODEL_NAME", "")
    if not base or not model:
        raise RuntimeError("no compatible endpoint configured")
    prompt = f"Chore: {description}"
    if stated:
        prompt += f"\nThe person measured {stated} minutes."
    reply = _post_json(
        f"{base}/chat/completions",
        {
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
        {"Authorization": f"Bearer {key}"} if key else None,
    )
    content = reply["choices"][0]["message"]["content"]
    data = _extract_json(content)
    return {**data, "lane": f"compatible:{model}"}


def _normalise(data: dict, fallback: dict) -> dict:
    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in {"automate", "delegate", "ignore"}:
        verdict = fallback["verdict"]
    try:
        minutes = _clamp(float(data.get("minutes", fallback["minutes"])))
    except (TypeError, ValueError):
        minutes = fallback["minutes"]
    reason = str(data.get("reason") or fallback["reason"]).strip()[:160]
    automation = data.get("automation")
    automation = str(automation).strip()[:60] if automation else None
    if verdict != "automate":
        automation = None
    return {
        "minutes": minutes,
        "verdict": verdict,
        "reason": reason,
        "automation": automation or fallback["automation"],
        "lane": data.get("lane", "rules"),
    }


def estimate(description: str, stated_minutes: int | None = None) -> dict:
    """Estimate one chore across the lanes, then reconcile it."""
    description = " ".join(description.split())
    if not description:
        raise ValueError("description is required")

    floor = rules_estimate(description)
    counted = _counted(description)

    model = None
    forced = config.setting("SLOTH_FORCE_RULES") == "1"
    for lane in (() if forced else (_ask_compatible,)):
        try:
            model = _normalise(lane(description, stated_minutes), floor)
            break
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except Exception:  # noqa: BLE001 - diagnostics must never raise
                detail = ""
            print(f"[lane] {lane.__name__} HTTP {exc.code}: {detail}", flush=True)
            continue
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, RuntimeError) as exc:
            print(f"[lane] {lane.__name__} unavailable: {type(exc).__name__}: {exc}", flush=True)
            continue

    chosen = model or floor

    if stated_minutes and stated_minutes > 0:
        minutes = _clamp(stated_minutes)
        evidence = f"measured by hand ({minutes} min)"
    elif counted:
        minutes = floor["minutes"]
        evidence = floor["evidence"]
    else:
        minutes = chosen["minutes"]
        evidence = "model estimate, no countable quantity"

    return {
        "description": description,
        "minutes": minutes,
        "verdict": chosen["verdict"],
        "reason": chosen["reason"],
        "automation": chosen["automation"],
        "evidence": evidence,
        "lane": chosen["lane"],
    }


def lanes_available() -> list[str]:
    """Only lanes that can actually answer. A lane badge that lies about a
    model being configured is the one thing this product cannot do."""
    lanes = ["rules"]
    if config.setting("MODEL_BASE_URL") and config.setting("MODEL_NAME"):
        lanes.append(f"api:{config.setting('MODEL_NAME')}")
    return lanes
