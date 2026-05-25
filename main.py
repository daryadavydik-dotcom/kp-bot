import asyncio
import logging

from config import config
from handlers import register_handlers
from max_bot import MaxBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    if not config.MAX_BOT_TOKEN:
        raise RuntimeError("Укажите MAX_BOT_TOKEN в файле .env")
    if not config.WEBHOOK_URL:
        raise RuntimeError("Укажите WEBHOOK_URL в файле .env")

    webhook_url = config.WEBHOOK_URL

    print()
    print("=" * 60)
    print("BOT STARTED")
    print("=" * 60)
    print(f"Webhook URL: {webhook_url}")
    print("=" * 60)
    print()
    logger.info("Webhook URL: %s", webhook_url)

    bot = MaxBot(token=config.MAX_BOT_TOKEN, port=config.PORT)
    register_handlers(bot)

    print("Registering webhook with MAX Bot API...")
    ok = await bot.register_webhook(webhook_url)
    if ok:
        print("Webhook registered successfully!")
    else:
        print("WARNING: Webhook registration failed.")
        print("You may need to register it manually via MAX portal.")
    print()

    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
