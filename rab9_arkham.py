import logging

from telegram.ext import Application

from config import TELEGRAM_BOT_TOKEN
from handlers import register_handlers
from alerts import post_init


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logging.getLogger("httpx").setLevel(logging.WARNING)

logger = logging.getLogger("rab9_crypto_intel_bot")


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Missing required env variable: TELEGRAM_BOT_TOKEN")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    register_handlers(app)

    logger.info("RAB9 Crypto Intel Bot started")
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
