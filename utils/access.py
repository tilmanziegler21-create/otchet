"""Фильтры доступа: админские хендлеры недоступны работникам."""

from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message, TelegramObject

from config import config


def _user_id(event: TelegramObject) -> int | None:
    user = getattr(event, "from_user", None)
    return user.id if user else None


class IsAdmin(BaseFilter):
    """Пропускает только Telegram ID из ADMIN_IDS."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return config.is_admin(_user_id(event))


class IsNotAdmin(BaseFilter):
    async def __call__(self, event: Message | CallbackQuery) -> bool:
        return not config.is_admin(_user_id(event))
