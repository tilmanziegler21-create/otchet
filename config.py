"""Конфигурация проекта. Все секреты читаются из .env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


def _parse_admin_ids(raw: str | None) -> tuple[int, ...]:
    """Разбирает список ID администраторов: '111,222 333;444'."""
    if not raw:
        return ()
    cleaned = raw.replace(";", ",").replace(" ", ",")
    ids: list[int] = []
    for chunk in cleaned.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.append(int(chunk))
        except ValueError:
            continue
    return tuple(dict.fromkeys(ids))


def _parse_hour(raw: str | None, default: int) -> int:
    """Час суточного бэкапа, 0-23. Мусор и выход за границы -> значение по умолчанию."""
    try:
        hour = int((raw or "").strip())
    except ValueError:
        return default
    return hour if 0 <= hour <= 23 else default


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: tuple[int, ...]
    db_path: Path
    currency: str
    backup_hour: int

    def is_admin(self, telegram_id: int | None) -> bool:
        return telegram_id is not None and telegram_id in self.admin_ids


def load_config() -> Config:
    db_path = Path(os.getenv("DB_PATH", str(BASE_DIR / "bot.db")))
    if not db_path.is_absolute():
        db_path = BASE_DIR / db_path
    return Config(
        bot_token=(os.getenv("BOT_TOKEN") or "").strip(),
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS")),
        db_path=db_path,
        currency=(os.getenv("CURRENCY") or "€").strip(),
        backup_hour=_parse_hour(os.getenv("BACKUP_HOUR"), 3),
    )


config = load_config()
