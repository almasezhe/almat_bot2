import asyncio
import logging
import sys
from os import getenv
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message



from private.handlers.priv_handler import router as private_start_router
from group.handlers.pub_handler import router as group_start_router


load_dotenv()
TOKEN = getenv("BOT_TOKEN")





if not TOKEN:
    raise RuntimeError("BOT_TOKEN not found in .env")

dp = Dispatcher()



async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    dp.include_router(private_start_router)
    dp.include_router(group_start_router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())



    