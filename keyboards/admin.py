"""Клавиатуры админ-панели."""

from __future__ import annotations

from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import Category, ReportBrief
from utils import dates
from utils.formatting import format_money

CB_MENU = "adm:menu"
CB_PRICES = "adm:prices"
CB_PRICE_SET = "adm:price_set"
CB_PRICE_EDIT = "adm:price_edit"
CB_CATEGORY_ADD = "adm:cat_add"
CB_REPORTS = "adm:reports"
CB_PICK_PREFIX = "adm:pick:"
CB_REPORT_PREFIX = "adm:report:"
CB_LIQUID_PREFIX = "adm:liquid:"
CB_CLOSE = "adm:close"

ACTION_PRICE_SET = "price_set"
ACTION_PRICE_EDIT = "price_edit"


def admin_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💰 Текущие закупочные цены", callback_data=CB_PRICES
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Установить закупочную цену", callback_data=CB_PRICE_SET
                )
            ],
            [
                InlineKeyboardButton(
                    text="✏️ Изменить закупочную цену", callback_data=CB_PRICE_EDIT
                )
            ],
            [
                InlineKeyboardButton(
                    text="🆕 Добавить категорию", callback_data=CB_CATEGORY_ADD
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗂 Сохраненные отчеты", callback_data=CB_REPORTS
                )
            ],
            [InlineKeyboardButton(text="✖️ Закрыть", callback_data=CB_CLOSE)],
        ]
    )


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ В админ-панель", callback_data=CB_MENU)]
        ]
    )


def categories_menu(
    categories: Sequence[Category], action: str, show_price: bool = False
) -> InlineKeyboardMarkup:
    rows = []
    for category in categories:
        title = category.name
        if show_price:
            title = f"{category.name} — {format_money(category.purchase_price)}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"{CB_PICK_PREFIX}{action}:{category.id}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=CB_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def liquid_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💧 Да, это жидкость", callback_data=f"{CB_LIQUID_PREFIX}1"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔧 Нет, устройство", callback_data=f"{CB_LIQUID_PREFIX}0"
                )
            ],
        ]
    )


def reports_menu(reports: Sequence[ReportBrief]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{dates.format_full(report.date)} — "
                f"{format_money(report.total_revenue)}",
                callback_data=f"{CB_REPORT_PREFIX}{report.id}",
            )
        ]
        for report in reports
    ]
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=CB_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)
