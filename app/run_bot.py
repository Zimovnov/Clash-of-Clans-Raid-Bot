import asyncio

from aiogram import Bot

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.integrations.telegram.command_menu import setup_command_menus
from app.integrations.telegram.router import build_dispatcher
from app.jobs.scheduler import AppScheduler


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not configured")

    bot = Bot(token=settings.bot_token)
    dp = build_dispatcher()
    await setup_command_menus(bot)

    scheduler = AppScheduler(bot)
    scheduler.start()

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
