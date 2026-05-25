"""
Portage of merge_client_answer.js:
- Takes the pending request saved in SQLite
- Parses client fields from the second operator message
- Merges with previously saved client fields
- If still missing → asks again; if complete → returns ready_for_kp
"""
import re

REQUIRED_FIELDS = ["client_name", "contact_person", "phone", "manager"]
OPTIONAL_FIELDS = [
    "client_name", "contact_person", "phone", "manager",
    "delivery_time", "payment_terms", "company_contacts",
]

_FIELD_LABELS = {
    "client_name": "название клиента",
    "contact_person": "контактное лицо",
    "phone": "телефон",
    "manager": "менеджера",
    "delivery_time": "срок поставки",
    "payment_terms": "условия оплаты",
    "company_contacts": "контакты компании",
}

_SKIP_RE = re.compile(
    r"(не\s*нужно|не\s*надо|без\s*данных|без\s*клиента|пропусти|пропустить|сформируй\s+без)",
    re.IGNORECASE,
)


def _parse_inline(text: str) -> dict:
    """Parse comma-separated positional data: company, contact, phone, manager."""
    parts = [p.strip() for p in text.split(",") if p.strip()]
    if len(parts) < 2:
        return {}

    phone_idx = next(
        (i for i, p in enumerate(parts) if len(re.sub(r"\D", "", p)) >= 7),
        None,
    )

    if phone_idx is None:
        keys = ["client_name", "contact_person", "phone", "manager"]
        return {keys[i]: p for i, p in enumerate(parts) if i < len(keys)}

    result = {"phone": parts[phone_idx]}
    before = parts[:phone_idx]
    after = parts[phone_idx + 1:]

    if len(before) >= 2:
        result["client_name"] = before[0]
        result["contact_person"] = " ".join(before[1:])
    elif len(before) == 1:
        result["client_name"] = before[0]

    if after:
        result["manager"] = after[0]

    return result


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
        elif re.match(r"^(телефон|phone|номер)$", key, re.IGNORECASE):
            result["phone"] = value
        elif re.match(r"^(менеджер|manager)$", key, re.IGNORECASE):
            result["manager"] = value
        elif re.match(r"^(срок|срок поставки|поставка|delivery)$", key, re.IGNORECASE):
            result["delivery_time"] = value
        elif re.match(r"^(оплата|условия оплаты|payment)$", key, re.IGNORECASE):
            result["payment_terms"] = value
        elif re.match(r"^(контакты компании|контакты|company contacts)$", key, re.IGNORECASE):
            result["company_contacts"] = value

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
                + "\n\nМожно дописать эти поля или ответить: без данных"
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
