"""Общие команды: /start, /cancel и кнопка отмены."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from config import config
from keyboards.employee import BTN_CANCEL, main_menu

router = Router(name="common")

# Подключается последним: ловит все, что не обработали остальные роутеры.
fallback_router = Router(name="fallback")

WELCOME_EMPLOYEE = (
    "Привет! 👋\n\n"
    "Здесь ты каждый день заполняешь продажи по категориям.\n\n"
    "Нажми «🆕 Новый отчет», чтобы начать."
)

WELCOME_ADMIN = (
    "Привет! 👋\n\n"
    "Ты вошел как администратор.\n\n"
    "• /admin — админ-панель (закупочные цены, категории, отчеты)\n"
    "• /report_today — отчет за сегодня\n"
    "• /reports — сохраненные отчеты"
)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user is None:
        return
    role = await db.register_user(message.from_user.id)
    is_admin = role == db.ROLE_ADMIN
    await message.answer(
        WELCOME_ADMIN if is_admin else WELCOME_EMPLOYEE,
        reply_markup=main_menu(is_admin),
    )


@router.message(Command("cancel"))
@router.message(F.text == BTN_CANCEL)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    current_state = await state.get_state()
    await state.clear()
    is_admin = config.is_admin(message.from_user.id)
    text = "Отменено." if current_state else "Сейчас нечего отменять."
    await message.answer(text, reply_markup=main_menu(is_admin))


@fallback_router.message(StateFilter(None))
async def unknown_message(message: Message) -> None:
    if message.from_user is None:
        return
    await message.answer(
        "Не понял. Воспользуйтесь кнопками меню.",
        reply_markup=main_menu(config.is_admin(message.from_user.id)),
    )


@fallback_router.callback_query()
async def outdated_callback(callback: CallbackQuery) -> None:
    await callback.answer("Кнопка больше не активна", show_alert=True)
