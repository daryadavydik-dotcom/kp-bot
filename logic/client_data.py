"""
Portage of check_client_data.js:
- Checks if all client fields are present in the operator message
- If missing and not "без данных" → returns need_client_data with question
- If "без данных" → returns empty client, ready_for_kp
"""
import re

REQUIRED_FIELDS = [
    {"key": "client_name", "label": "название клиента"},
    {"key": "contact_person", "label": "контактное лицо"},
]

OPTIONAL_FIELDS = REQUIRED_FIELDS

_SKIP_RE = re.compile(
    r"(не\s*нужно|не\s*надо|без\s*данных|без\s*клиента|пропусти|пропустить|сформируй\s+без)",
    re.IGNORECASE,
)


def check_client_data(message_text: str, kp_data: dict, chat_id: str) -> dict:
    client = {
        f["key"]: str(kp_data.get(f["key"], "") or "")
        for f in OPTIONAL_FIELDS
    }

    wants_skip = bool(_SKIP_RE.search(message_text))
    missing = [f for f in REQUIRED_FIELDS if not client[f["key"]].strip()]

    if missing and not wants_skip:
        missing_labels = "\n".join(f"- {f['label']}" for f in missing)
        question = (
            "Не хватает данных для КП.\n\n"
            f"Пришлите, пожалуйста:\n{missing_labels}\n\n"
            "Можно одной строкой через запятую:\n"
            "ООО Север, Иван Иванов\n\n"
            "Или в столбик:\n"
            "Клиент: ООО Север\n"
            "Контакт: Иван Иванов\n\n"
            "Если эти данные не нужны, напишите: без данных"
        )
        return {
            **kp_data,
            "status": "need_client_data",
            "chat_id": str(chat_id),
            "question": question,
            "pending": {
                "chat_id": str(chat_id),
                "request_text": message_text,
                "items": kp_data.get("items", []),
                "product_warning_text": kp_data.get("product_warning_text", ""),
                "not_found_items": kp_data.get("not_found_items", []),
                "price_missing_items": kp_data.get("price_missing_items", []),
                "client": client,
            },
        }

    return {
        **kp_data,
        "status": "ready_for_kp",
        "chat_id": str(chat_id),
        "request_text": message_text,
        "client": {f["key"]: "" for f in OPTIONAL_FIELDS} if wants_skip else client,
    }
