"""Клавиатуры работника: простой интерфейс на кнопках."""

from __future__ import annotations

from typing import Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from database import ReportBrief
from utils import dates

BTN_NEW_REPORT = "🆕 Новый отчет"
BTN_TODAY_REPORT = "📅 Отчет за сегодня"
BTN_MY_REPORTS = "🗂 Мои отчеты"
BTN_ADMIN_PANEL = "🛠 Админ-панель"
BTN_CANCEL = "❌ Отмена"
BTN_TODAY_DATE_PREFIX = "📆 Сегодня"

CB_CONFIRM = "report:confirm"
CB_EDIT = "report:edit"
CB_BACK = "report:back"
CB_EDIT_CATEGORY = "report:edit:cat:"
CB_EDIT_CUSTOMERS = "report:edit:customers"
CB_EMPLOYEE_REPORT = "emp:report:"


def today_button_text() -> str:
    return f"{BTN_TODAY_DATE_PREFIX} ({dates.format_full(dates.today())})"


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=BTN_NEW_REPORT)],
        [KeyboardButton(text=BTN_TODAY_REPORT), KeyboardButton(text=BTN_MY_REPORTS)],
    ]
    if is_admin:
        rows.append([KeyboardButton(text=BTN_ADMIN_PANEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]], resize_keyboard=True
    )


def date_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=today_button_text())],
            [KeyboardButton(text=BTN_CANCEL)],
        ],
        resize_keyboard=True,
    )


def preview_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data=CB_CONFIRM)],
            [InlineKeyboardButton(text="✏️ Исправить", callback_data=CB_EDIT)],
        ]
    )


def edit_menu(names: Sequence[str]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=name, callback_data=f"{CB_EDIT_CATEGORY}{index}"
            )
        ]
        for index, name in enumerate(names)
    ]
    rows.append(
        [InlineKeyboardButton(text="👥 Покупателей", callback_data=CB_EDIT_CUSTOMERS)]
    )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=CB_BACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def employee_reports_menu(reports: Sequence[ReportBrief]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=dates.format_full(report.date),
                callback_data=f"{CB_EMPLOYEE_REPORT}{report.id}",
            )
        ]
        for report in reports
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
