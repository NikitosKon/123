"""Entrypoint: bot + collector worker + health API."""
from __future__ import annotations

import asyncio
import logging

import uvicorn
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import setup_dispatcher
from app.config import get_settings
from app.workers.poller import CollectorWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("main")


async def amain() -> None:
    settings = get_settings()
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN не задан — укажите его в .env или переменных окружения")

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = setup_dispatcher(settings)

    worker = CollectorWorker(bot, notify_chat_ids=settings.admin_id_list)

    from app.api.health import app as api_app

    api = uvicorn.Server(uvicorn.Config(api_app, host="0.0.0.0", port=8080, log_level="warning"))

    log.info("starting: bot polling + collector + :8080/health")
    await asyncio.gather(
        dp.start_polling(bot),
        worker.run(),
        api.serve(),
    )


if __name__ == "__main__":
    asyncio.run(amain())
