import asyncio
import logging

from pyngrok import ngrok, conf as ngrok_conf

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

    if config.NGROK_AUTH_TOKEN:
        ngrok_conf.get_default().auth_token = config.NGROK_AUTH_TOKEN

    tunnel = ngrok.connect(config.PORT, "http")
    webhook_url = tunnel.public_url + "/webhook"

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

    # Register webhook with MAX Bot API automatically
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
