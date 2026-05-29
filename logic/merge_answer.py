"""
Portage of merge_client_answer.js:
- Takes the pending request saved in SQLite
- Parses client fields from the second operator message
- Merges with previously saved client fields
- If still missing → asks again; if complete → returns ready_for_kp
"""
import re

REQUIRED_FIELDS = ["client_name", "contact_person"]
OPTIONAL_FIELDS = ["client_name", "contact_person"]

_FIELD_LABELS = {
    "client_name": "название клиента",
    "contact_person": "контактное лицо",
}

_SKIP_RE = re.compile(
    r"(не\s*нужно|не\s*надо|без\s*данных|без\s*клиента|пропусти|пропустить|сформируй\s+без)",
    re.IGNORECASE,
)


def _parse_inline(text: str) -> dict:
    """Parse comma-separated positional data: company, contact."""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) < 2:
        return {}
    return {"client_name": parts[0], "contact_person": " ".join(parts[1:])}


def _parse_client_fields(text: str) -> dict:
    result = {}
    lines = [ln.strip() for ln in re.split(r"\r?\n|\\n|;", str(text)) if ln.strip()]

    for line in lines:
        m = re.match(r"^([^:=\-]+)\s*[:=\-]\s*(.+)$", line)
        if not m:
            continue
        key = m.group(1).strip().lower()
        value = m.group(2).strip()

        if re.match(r"^(клиент|компания|организация|client)$", key, re.IGNORECASE):
            result["client_name"] = value
        elif re.match(r"^(контакт|контактное лицо|фио|contact)$", key, re.IGNORECASE):
            result["contact_person"] = value

    # If labeled parsing found nothing, try comma-separated inline format
    if not result:
        result = _parse_inline(text)

    return result


def merge_client_answer(pending: dict, message_text: str) -> dict:
    """Merge second operator message with saved pending request."""
    previous_client = pending.get("client", {})
    wants_skip = bool(_SKIP_RE.search(message_text))

    if wants_skip:
        client = {key: "" for key in OPTIONAL_FIELDS}
    else:
        parsed = _parse_client_fields(message_text)
        client = {**previous_client, **parsed}

    missing = [key for key in REQUIRED_FIELDS if not str(client.get(key, "") or "").strip()]

    if missing and not wants_skip:
        return {
            **pending,
            "status": "need_client_data",
            "chat_id": pending.get("chat_id"),
            "question": (
                "Принял. Ещё не хватает:\n"
                + "\n".join(f"- {_FIELD_LABELS[k]}" for k in missing if k in _FIELD_LABELS)
                + "\n\nМожно дописать или ответить: без данных"
            ),
            "pending": {**pending, "client": client},
        }

    return {
        "status": "ready_for_kp",
        "chat_id": pending.get("chat_id"),
        "items": pending.get("items", []),
        "product_warning_text": pending.get("product_warning_text", ""),
        "not_found_items": pending.get("not_found_items", []),
        "price_missing_items": pending.get("price_missing_items", []),
        "client": client,
        "request_text": pending.get("request_text", ""),
    }
