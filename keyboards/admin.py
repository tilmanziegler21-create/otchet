"""Клавиатуры админ-панели."""

from __future__ import annotations

from typing import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from database import Category, City, ReportBrief
from utils import dates
from utils.formatting import format_money

CB_MENU = "adm:menu"
CB_PRICES = "adm:prices"
CB_PRICE_SET = "adm:price_set"
CB_PRICE_EDIT = "adm:price_edit"
CB_CATEGORY_ADD = "adm:cat_add"
CB_CITIES = "adm:cities"
CB_CITY_ADD = "adm:city_add"
CB_CITY_CARD = "adm:city:"
CB_CITY_TOGGLE = "adm:city_toggle:"
CB_CITY_SALARY = "adm:city_salary:"
CB_SALARY_KIND = "adm:salary_kind:"
CB_CITY_PLAN = "adm:city_plan:"
CB_PLAN_MONTH = "adm:plan_month:"
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
            [InlineKeyboardButton(text="🏙 Города", callback_data=CB_CITIES)],
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


def cities_menu(cities: Sequence[City]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{'🏙' if city.active else '🚫'} {city.name}",
                callback_data=f"{CB_CITY_CARD}{city.id}",
            )
        ]
        for city in cities
    ]
    rows.append(
        [InlineKeyboardButton(text="➕ Добавить город", callback_data=CB_CITY_ADD)]
    )
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=CB_MENU)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def city_card_menu(city: City) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💵 Минус работникам",
                    callback_data=f"{CB_CITY_SALARY}{city.id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎯 План на месяц",
                    callback_data=f"{CB_CITY_PLAN}{city.id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Выключить город" if city.active else "✅ Включить город",
                    callback_data=f"{CB_CITY_TOGGLE}{city.id}",
                )
            ],
            [InlineKeyboardButton(text="⬅️ К городам", callback_data=CB_CITIES)],
        ]
    )


def salary_kind_menu(city_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📊 Процент от оборота",
                    callback_data=f"{CB_SALARY_KIND}percent:{city_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="💶 Фикс за день",
                    callback_data=f"{CB_SALARY_KIND}fixed:{city_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🗓 Фикс за месяц",
                    callback_data=f"{CB_SALARY_KIND}monthly:{city_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Назад", callback_data=f"{CB_CITY_CARD}{city_id}"
                )
            ],
        ]
    )


def plan_months_menu(
    city_id: int, months: Sequence[tuple[str, float]]
) -> InlineKeyboardMarkup:
    rows = []
    for month, amount in months:
        value = format_money(amount) if amount > 0 else "не задан"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{dates.format_month(month)} — {value}",
                    callback_data=f"{CB_PLAN_MONTH}{month}:{city_id}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{CB_CITY_CARD}{city_id}")]
    )
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
