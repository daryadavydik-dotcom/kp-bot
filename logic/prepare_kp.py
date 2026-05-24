"""
Portage of prepare_kp_data.js:
- Parses operator request into items + quantities
- Searches nomenclature for each item (fuzzy token matching, threshold 55)
- Returns found items, warnings about missing/no-price items
"""
import math
import re


# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------

def _normalize_header(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower().replace("ё", "е")).strip()


def _normalize_text(value) -> str:
    text = str(value or "").lower().replace("ё", "е")
    text = re.sub(r"[^\w/.,\s\-]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _first_value(source: dict, keys: list[str]) -> str:
    """Get first non-empty value from dict with flexible key matching (mirrors JS firstValue)."""
    if not source or not isinstance(source, dict):
        return ""

    # 1. Direct key match
    for key in keys:
        value = source.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()

    # 2. Normalised key match
    norm_keys = {_normalize_header(k) for k in keys}
    for src_key, value in source.items():
        if _normalize_header(src_key) in norm_keys:
            if value is not None and str(value).strip():
                return str(value).strip()

    # 3. Substring match (key length >= 4)
    for src_key, value in source.items():
        norm_src = _normalize_header(src_key)
        for key in keys:
            norm_key = _normalize_header(key)
            if len(norm_key) >= 4 and norm_key in norm_src:
                if value is not None and str(value).strip():
                    return str(value).strip()

    return ""


# ---------------------------------------------------------------------------
# Quantity parsing
# ---------------------------------------------------------------------------

_QTY_PATTERNS = [
    re.compile(r"[-–—]\s*(\d+(?:[.,]\d+)?)\s*(?:шт\.?|штук|компл\.?|комплект(?:а|ов)?)", re.IGNORECASE),
    re.compile(r"(?:кол-?во|количество)\s*[:=\-]?\s*(\d+(?:[.,]\d+)?)", re.IGNORECASE),
    re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:шт\.?|штук|компл\.?|компл(?:ект)?(?:а|ов)?)", re.IGNORECASE),
]


def _parse_quantity(text: str) -> float:
    normalized = re.sub(r"\s+", " ", str(text)).strip()
    for pattern in _QTY_PATTERNS:
        m = pattern.search(normalized)
        if m:
            return float(m.group(1).replace(",", "."))
    return 1


def _remove_quantity(text: str) -> str:
    result = re.sub(
        r"[-–—]\s*\d+(?:[.,]\d+)?\s*(?:шт\.?|штук|компл\.?|комплект(?:а|ов)?)",
        " ", str(text), flags=re.IGNORECASE,
    )
    result = re.sub(
        r"\d+(?:[.,]\d+)?\s*(?:шт\.?|штук|компл\.?|компл(?:ект)?(?:а|ов)?)",
        " ", result, flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", result).strip()


# ---------------------------------------------------------------------------
# Query cleaning
# ---------------------------------------------------------------------------

def _clean_product_query(text: str) -> str:
    result = re.sub(r"^\s*(?:\d+[).:\-]?|[-*•])\s*", "", str(text or ""), flags=re.UNICODE)
    result = re.sub(r"\s+", " ", result).strip()

    for _ in range(3):
        result = re.sub(
            r"^(?:добрый день|доброе утро|добрый вечер|здравствуйте|привет)[!.,\s]*",
            "", result, flags=re.IGNORECASE,
        ).strip()
        result = re.sub(
            r"^(?:прошу|просьба)\s+(?:выставить|составить|сформировать|подготовить)"
            r"\s+(?:счет|счёт|кп|коммерческое предложение)\s*(?:на|по)?\s*",
            "", result, flags=re.IGNORECASE,
        ).strip()
        result = re.sub(
            r"^(?:выставьте|сформируйте|сделайте|подготовьте)\s*"
            r"(?:счет|счёт|кп|коммерческое предложение)?\s*(?:на|по)?\s*",
            "", result, flags=re.IGNORECASE,
        ).strip()
        result = re.sub(r"^(?:нужно|надо)\s*", "", result, flags=re.IGNORECASE).strip()

    return _remove_quantity(result)


def _parse_requested_items(text: str) -> list[dict]:
    raw_lines = [ln.strip() for ln in re.split(r"\r?\n|;", str(text or "")) if ln.strip()]
    lines = raw_lines if len(raw_lines) > 1 else [str(text or "")]

    items = [
        {"original": ln, "query": _clean_product_query(ln), "qty": _parse_quantity(ln)}
        for ln in lines
        if len(_clean_product_query(ln)) >= 2
    ]

    if items:
        return items

    fallback = _clean_product_query(text)
    return [{"original": str(text or ""), "query": fallback, "qty": _parse_quantity(text)}] if fallback else []


# ---------------------------------------------------------------------------
# Nomenclature matching
# ---------------------------------------------------------------------------

def _token_score(query: str, candidate: str) -> int:
    query_norm = _normalize_text(query)
    candidate_norm = _normalize_text(candidate)

    query_tokens = [t for t in query_norm.split(" ") if len(t) >= 2]
    if not query_tokens or not candidate_norm:
        return 0

    if query_norm in candidate_norm:   # candidate contains query
        return 100
    if candidate_norm in query_norm:   # query contains candidate
        return 95

    matches = sum(1 for t in query_tokens if t in candidate_norm)
    return round(matches / len(query_tokens) * 90)


def _build_product(row: dict) -> dict:
    official_name = _first_value(row, [
        "official_name", "name", "product",
        "Наименование", "Наименование товара", "Официальное наименование",
        "Номенклатура", "Номенклатура товара", "Название", "Название товара", "Товар",
    ])
    aliases = _first_value(row, [
        "aliases", "alias", "search_text", "query",
        "Запрос", "Синонимы", "Поисковые слова",
    ])
    price_text = _first_value(row, [
        "price", "unit_price",
        "Цена", "Цена с НДС", "Цена без НДС", "Цена, руб", "Стоимость", "Стоимость с НДС", "Прайс",
    ])

    normalized = re.sub(r"\s", "", str(price_text)).replace(",", ".")
    try:
        price = float(normalized) if normalized else float("nan")
    except ValueError:
        price = float("nan")

    unit = _first_value(row, [
        "unit", "units", "Ед. изм.", "Ед.изм.", "ед. изм.", "ед.изм.",
        "Единица", "Единица измерения", "Ед", "ед.",
    ])

    return {
        "official_name": official_name,
        "aliases": aliases,
        "price": price if math.isfinite(price) else "",
        "unit": unit,
    }


def _find_best(query: str, products: list[dict]) -> dict | None:
    if not products:
        return None
    scored = [
        {**p, "score": max(_token_score(query, p["official_name"]), _token_score(query, p["aliases"]))}
        for p in products
    ]
    return max(scored, key=lambda x: x["score"])


def _warning_text(not_found: list, price_missing: list) -> str:
    parts = []
    if not_found:
        lines = "\n".join(f"- {item['query']}" for item in not_found)
        parts.append(f"Не найдены в номенклатуре:\n{lines}")
    if price_missing:
        lines = "\n".join(f"- {item['product']}" for item in price_missing)
        parts.append(f"Найдены, но без цены:\n{lines}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def prepare_kp_data(request_text: str, chat_id: str, product_rows: list[dict]) -> dict:
    """Parse request, match nomenclature, return items + warnings."""
    if not product_rows:
        return {
            "chat_id": str(chat_id),
            "request_text": request_text,
            "status": "product_lookup_failed",
            "stop_reason": "products_db_missing",
            "question": "Не удалось прочитать базу номенклатуры.\n\nПроверьте файл номенклатуры на Яндекс.Диске.",
        }

    requested = _parse_requested_items(request_text)
    products = [p for p in (_build_product(row) for row in product_rows) if p["official_name"]]

    found, not_found, price_missing = [], [], []

    for req in requested:
        best = _find_best(req["query"], products)
        if not best or best["score"] < 55:
            not_found.append(req)
            continue
        if best["price"] == "":
            price_missing.append({"query": req["query"], "product": best["official_name"]})
            continue
        found.append({
            "product": best["official_name"],
            "unit": best.get("unit", ""),
            "qty": req["qty"],
            "price": best["price"],
            "matched_product_score": best["score"],
            "source_query": req["query"],
        })

    if not found:
        warn = _warning_text(not_found, price_missing)
        return {
            "chat_id": str(chat_id),
            "request_text": request_text,
            "status": "product_lookup_failed",
            "stop_reason": "product_not_found",
            "product_query": "; ".join(r["query"] for r in requested),
            "not_found_items": not_found,
            "price_missing_items": price_missing,
            "question": f"Не удалось найти позиции для КП.\n\n{warn}\n\nОбновите базу товаров или проверьте формулировку заявки.",
        }

    warn = _warning_text(not_found, price_missing)
    return {
        "chat_id": str(chat_id),
        "request_text": request_text,
        "status": "products_ready_with_warnings" if warn else "products_ready",
        "product_warning_text": warn,
        "not_found_items": not_found,
        "price_missing_items": price_missing,
        "items": found,
    }
