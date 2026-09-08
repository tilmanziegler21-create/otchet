"""Бэкап базы: копия уходит администраторам в Telegram.

Диск Render не теряет данные при деплое и рестарте, но своя копия нужна на
случай, когда база повреждена или сервис удален. Копия снимается через
`VACUUM INTO` — это консистентный снимок SQLite без остановки бота.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import aiosqlite
from aiogram import Bot
from aiogram.types import FSInputFile

import database as db
from config import config

logger = logging.getLogger(__name__)


async def create_backup() -> Path:
    """Снимает копию базы во временный файл и возвращает путь к нему."""
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    target = Path(tempfile.gettempdir()) / f"otchet-{stamp}.db"
    target.unlink(missing_ok=True)
    async with aiosqlite.connect(config.db_path) as connection:
        await connection.execute("VACUUM INTO ?", (str(target),))
    return target


async def _caption() -> str:
    cities = await db.get_cities()
    reports = await db.count_reports()
    return (
        f"💾 Бэкап базы за {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        f"Городов: {len(cities)}\n"
        f"Отчетов: {reports}"
    )


async def send_backup(bot: Bot, chat_ids: tuple[int, ...] | None = None) -> bool:
    """Отправляет копию базы администраторам. False — отправить не удалось."""
    targets = chat_ids if chat_ids is not None else config.admin_ids
    if not targets:
        logger.warning("Бэкап не отправлен: список администраторов пуст")
        return False

    try:
        path = await create_backup()
    except Exception:
        logger.exception("Не удалось снять копию базы")
        return False

    caption = await _caption()
    sent = False
    try:
        for chat_id in targets:
            try:
                await bot.send_document(
                    chat_id, FSInputFile(path, filename=path.name), caption=caption
                )
                sent = True
            except Exception:
                logger.exception("Бэкап не ушел администратору %s", chat_id)
    finally:
        path.unlink(missing_ok=True)
    return sent


def seconds_until(hour: int, now: datetime | None = None) -> float:
    """Сколько секунд до ближайшего `hour`:00 по времени сервера."""
    now = now or datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def backup_scheduler(bot: Bot) -> None:
    """Раз в сутки в заданный час присылает копию базы администраторам."""
    while True:
        await asyncio.sleep(seconds_until(config.backup_hour))
        logger.info("Отправляю суточный бэкап базы")
        await send_backup(bot)
