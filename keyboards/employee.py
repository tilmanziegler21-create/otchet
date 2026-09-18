"""Клавиатуры работника: простой интерфейс на кнопках."""

from __future__ import annotations

from typing import Sequence

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from database import City, ReportBrief
from keyboards.admin import REPORTS_PAGE_SIZE, page_nav
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
CB_CITY = "report:city:"
CB_EDIT_CATEGORY = "report:edit:cat:"
CB_EDIT_CUSTOMERS = "report:edit:customers"
CB_EDIT_CITY = "report:edit:city"
CB_EDIT_OUTREACH = "report:edit:outreach"
CB_EDIT_ITEMS = "report:edit:items"
CB_PICK = "report:pick:id:"
CB_PICK_DONE = "report:pick:done"
CB_PICK_NONE = "report:pick:none"
CB_EMPLOYEE_REPORT = "emp:report:"
CB_EMP_REPORTS_PAGE = "emp:rpage:"


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


def cities_menu(cities: Sequence[City]) -> InlineKeyboardMarkup:
    """Выбор города в начале отчета — по кнопке на каждый город."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"🏙 {city.name}", callback_data=f"{CB_CITY}{city.id}"
                )
            ]
            for city in cities
        ]
    )


def picker_menu(
    items: Sequence[tuple[int, str]], chosen: Sequence[int]
) -> InlineKeyboardMarkup:
    """Список позиций группы с галочками. `items` — пары (id позиции, название)."""
    picked = set(chosen)
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'☑️' if item_id in picked else '⬜️'} {name}",
                callback_data=f"{CB_PICK}{item_id}",
            )
        ]
        for item_id, name in items
    ]
    if picked:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✅ Готово ({len(picked)})", callback_data=CB_PICK_DONE
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="➡️ Не продавалось", callback_data=CB_PICK_NONE)]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    rows.append(
        [InlineKeyboardButton(text="📨 Рассылки", callback_data=CB_EDIT_OUTREACH)]
    )
    rows.append(
        [InlineKeyboardButton(text="🧾 Список позиций", callback_data=CB_EDIT_ITEMS)]
    )
    rows.append([InlineKeyboardButton(text="🏙 Город", callback_data=CB_EDIT_CITY)])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=CB_BACK)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def employee_reports_menu(
    reports: Sequence[ReportBrief],
    page: int = 0,
    total: int = 0,
    page_size: int = REPORTS_PAGE_SIZE,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=(
                    dates.format_full(report.date)
                    + (f" · {report.city_name}" if report.city_name else "")
                ),
                callback_data=f"{CB_EMPLOYEE_REPORT}{report.id}",
            )
        ]
        for report in reports
    ]
    rows.extend(page_nav(CB_EMP_REPORTS_PAGE, page, total, page_size))
    return InlineKeyboardMarkup(inline_keyboard=rows)
