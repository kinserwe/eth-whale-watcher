import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.handlers import router
from app.bot.notify import notify_loop
from app.config import settings
from app.logging_config import configure_logging
from app.tokens import USDT


async def main() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    dp = Dispatcher()
    dp.include_router(router)
    token = USDT

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(dp.start_polling(bot))
            tg.create_task(notify_loop(bot, token))
    finally:
        await bot.session.close()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
