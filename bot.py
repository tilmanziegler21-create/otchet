"""Точка входа: запуск Telegram-бота (aiogram 3, long polling)."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import config
from database import StorageError, init_db
from handlers import get_routers
from services.backup import backup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

COMMANDS = (
    BotCommand(command="start", description="Начать работу"),
    BotCommand(command="report_today", description="Отчет за сегодня"),
    BotCommand(command="reports", description="Сохраненные отчеты"),
    BotCommand(command="admin", description="Админ-панель"),
    BotCommand(command="week", description="Отчет за неделю (админ)"),
    BotCommand(command="month", description="Отчет за месяц (админ)"),
    BotCommand(command="backup", description="Копия базы (админ)"),
    BotCommand(command="cancel", description="Отменить текущее действие"),
)


async def main() -> None:
    if not config.bot_token:
        logger.error("BOT_TOKEN не задан. Заполните .env (см. .env.example).")
        sys.exit(1)
    if not config.admin_ids:
        logger.warning(
            "ADMIN_IDS не заданы — админ-панель и полные отчеты будут недоступны."
        )

    try:
        await init_db()
    except StorageError as error:
        logger.error("%s", error)
        sys.exit(1)
    logger.info("База данных готова: %s", config.db_path)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_routers(*get_routers())

    await bot.set_my_commands(list(COMMANDS))
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен. Администраторы: %s", config.admin_ids or "—")

    # Суточный бэкап базы админам — страховка на случай потери диска.
    backup_task = asyncio.create_task(backup_scheduler(bot))
    logger.info("Бэкап базы будет уходить каждый день в %02d:00", config.backup_hour)
    try:
        await dispatcher.start_polling(bot)
    finally:
        backup_task.cancel()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен.")
