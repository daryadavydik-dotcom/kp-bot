import asyncio
import logging
import time
from datetime import date

from config import config
from database import Database
from logic.build_kp import build_replacements, fill_template
from logic.client_data import check_client_data
from logic.merge_answer import merge_client_answer
from logic.prepare_kp import prepare_kp_data
from max_bot import MaxBot
from yandex_disk import YandexDiskClient

logger = logging.getLogger(__name__)

db = Database(config.DATABASE_PATH)
yadisk = YandexDiskClient(config.YANDEX_DISK_TOKEN)

# In-memory nomenclature cache: reload every 5 minutes
_cache: dict = {"data": None, "loaded_at": 0.0}
_CACHE_TTL = 300


async def _get_nomenclature() -> list[dict]:
    now = time.monotonic()
    if _cache["data"] is None or now - _cache["loaded_at"] > _CACHE_TTL:
        logger.info("Loading nomenclature from Yandex Disk")
        _cache["data"] = await yadisk.load_nomenclature(config.YANDEX_DISK_NOMENCLATURE_PATH)
        _cache["loaded_at"] = now
    return _cache["data"]


_LOGOS_DIR = "/MFB/templates/logos"
_LOGO_KEYS = {
    "main": f"{_LOGOS_DIR}/logo_main.png",
    "right": f"{_LOGOS_DIR}/logo_right.png",
    "left_top": f"{_LOGOS_DIR}/logo_left_top.png",
    "left_bot": f"{_LOGOS_DIR}/logo_left_bot.png",
}


async def _download_logos() -> dict:
    """Download all logo files from Yandex Disk; skip any that fail."""
    import asyncio
    logos = {}

    async def _fetch(key: str, path: str):
        try:
            logos[key] = await yadisk.download_file(path)
        except Exception:
            pass

    await asyncio.gather(*[_fetch(k, p) for k, p in _LOGO_KEYS.items()])
    return logos


async def _create_and_send_kp(bot: MaxBot, chat_id: str, kp_data: dict) -> None:
    try:
        kp_number = db.next_kp_number()
        replacements = build_replacements(kp_data, kp_number)

        template_bytes, logos = await asyncio.gather(
            yadisk.download_file(config.YANDEX_DISK_TEMPLATE_PATH),
            _download_logos(),
        )
        filled_bytes = fill_template(template_bytes, replacements, logos)

        today_str = date.today().strftime("%Y-%m-%d")
        filename = f"КП_{kp_number}_{today_str}.xlsx"
        disk_path = f"{config.YANDEX_DISK_GENERATED_FOLDER}/{filename}"

        await yadisk.create_folder(config.YANDEX_DISK_GENERATED_FOLDER)
        await yadisk.upload_file(disk_path, filled_bytes)
        public_url = await yadisk.publish_and_get_url(disk_path)

        db.delete_pending(chat_id)

        product_warning_text = kp_data.get("product_warning_text", "")
        message = "КП готово:\n" + public_url
        if product_warning_text:
            message += "\n\nВнимание:\n" + product_warning_text

        await bot.send_text(chat_id, message)

    except Exception as exc:
        logger.exception("KP generation failed for chat_id=%s", chat_id)
        await bot.send_text(chat_id, f"Ошибка при генерации КП:\n{exc}")


def register_handlers(bot: MaxBot) -> None:
    @bot.on_message
    async def handle_message(chat_id: str, text: str) -> None:
        text = text.strip()

        # /start — greeting
        if text.lower() == "/start":
            await bot.send_text(chat_id, "Привет! Отправьте заявку на КП, и я сформирую коммерческое предложение.")
            return

        # /cancel — cancel pending request
        if text.lower() in ("/cancel", "отмена"):
            if db.get_pending(chat_id):
                db.delete_pending(chat_id)
                await bot.send_text(chat_id, "Заявка отменена. Пришлите новую.")
            else:
                await bot.send_text(chat_id, "Активных заявок нет.")
            return

        # /reload — force reload nomenclature cache
        if text.lower() == "/reload":
            _cache["data"] = None
            _cache["loaded_at"] = 0.0
            await bot.send_text(chat_id, "Номенклатура будет перезагружена при следующей заявке.")
            return

        pending = db.get_pending(chat_id)

        if pending:
            # Second message: merge client data with saved pending
            result = merge_client_answer(pending, text)

            if result["status"] == "need_client_data":
                db.save_pending(chat_id, result["pending"])
                await bot.send_text(chat_id, result["question"])
            elif result["status"] == "ready_for_kp":
                await bot.send_text(chat_id, "Генерирую КП...")
                await _create_and_send_kp(bot, chat_id, result)
            return

        # First message: new KP request
        try:
            products = await _get_nomenclature()
        except Exception as exc:
            logger.exception("Failed to load nomenclature")
            await bot.send_text(chat_id, f"Не удалось загрузить номенклатуру с Яндекс.Диска:\n{exc}")
            return

        kp_data = prepare_kp_data(text, chat_id, products)

        if kp_data["status"] == "product_lookup_failed":
            await bot.send_text(chat_id, kp_data["question"])
            return

        client_result = check_client_data(text, kp_data, chat_id)

        if client_result["status"] == "need_client_data":
            db.save_pending(chat_id, client_result["pending"])
            await bot.send_text(chat_id, client_result["question"])
        elif client_result["status"] == "ready_for_kp":
            await bot.send_text(chat_id, "Генерирую КП...")
            await _create_and_send_kp(bot, chat_id, client_result)
