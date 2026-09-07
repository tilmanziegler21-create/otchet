"""Админ-панель: закупочные цены, категории, сохраненные отчеты.

Все хендлеры закрыты фильтром IsAdmin — работник сюда не попадет.
"""

from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import database as db
from config import config
from keyboards.admin import (
    ACTION_PRICE_EDIT,
    ACTION_PRICE_SET,
    CB_CATEGORY_ADD,
    CB_CITIES,
    CB_CITY_ADD,
    CB_CITY_TOGGLE,
    CB_CLOSE,
    CB_LIQUID_PREFIX,
    CB_MENU,
    CB_PICK_PREFIX,
    CB_PRICE_EDIT,
    CB_PRICE_SET,
    CB_PRICES,
    CB_REPORT_PREFIX,
    CB_REPORTS,
    admin_menu,
    back_menu,
    categories_menu,
    cities_menu,
    liquid_menu,
    reports_menu,
)
from keyboards.employee import BTN_ADMIN_PANEL, cancel_menu
from services.calculations import summary_from_report
from services.report_builder import (
    render_cities,
    render_full_report,
    render_prices,
    render_reports_list,
)
from utils.access import IsAdmin, IsNotAdmin
from utils.formatting import format_money, parse_amount

router = Router(name="admin")

REPORTS_LIMIT = 10

MENU_TEXT = (
    "🛠 <b>Админ-панель</b>\n\n"
    "Здесь хранится внутренняя экономика. Работник этих данных не видит."
)


class AdminStates(StatesGroup):
    waiting_price = State()
    waiting_category_name = State()
    waiting_category_price = State()
    waiting_category_is_liquid = State()
    waiting_city_name = State()


# ------------------------------------------------------------ вход в панель


@router.message(Command("admin"), IsAdmin())
async def cmd_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(MENU_TEXT, reply_markup=admin_menu())


@router.message(F.text == BTN_ADMIN_PANEL, IsAdmin())
async def btn_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(MENU_TEXT, reply_markup=admin_menu())


@router.message(Command("admin"), IsNotAdmin())
async def cmd_admin_denied(message: Message) -> None:
    await message.answer("Команда недоступна.")


@router.callback_query(F.data == CB_MENU, IsAdmin())
async def back_to_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(MENU_TEXT, reply_markup=admin_menu())
    await callback.answer()


@router.callback_query(F.data == CB_CLOSE, IsAdmin())
async def close_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text("Админ-панель закрыта. /admin — открыть снова.")
    await callback.answer()


# ------------------------------------------------------------ закупочные цены


@router.callback_query(F.data == CB_PRICES, IsAdmin())
async def show_prices(callback: CallbackQuery) -> None:
    categories = await db.get_categories(only_active=False)
    if callback.message is not None:
        await callback.message.edit_text(
            render_prices(categories), reply_markup=back_menu()
        )
    await callback.answer()


@router.callback_query(F.data.in_({CB_PRICE_SET, CB_PRICE_EDIT}), IsAdmin())
async def choose_category_for_price(
    callback: CallbackQuery, state: FSMContext
) -> None:
    await state.clear()
    categories = await db.get_categories(only_active=False)
    if not categories:
        await callback.answer("Категорий пока нет", show_alert=True)
        return
    is_edit = callback.data == CB_PRICE_EDIT
    action = ACTION_PRICE_EDIT if is_edit else ACTION_PRICE_SET
    title = (
        "Какую закупочную цену изменить?"
        if is_edit
        else "Для какой категории установить закупочную цену?"
    )
    if callback.message is not None:
        await callback.message.edit_text(
            title,
            reply_markup=categories_menu(categories, action, show_price=is_edit),
        )
    await callback.answer()


@router.callback_query(F.data.startswith(CB_PICK_PREFIX), IsAdmin())
async def ask_price(callback: CallbackQuery, state: FSMContext) -> None:
    payload = (callback.data or "")[len(CB_PICK_PREFIX) :]
    action, _, raw_id = payload.partition(":")
    if action not in (ACTION_PRICE_SET, ACTION_PRICE_EDIT) or not raw_id.isdigit():
        await callback.answer("Некорректный выбор", show_alert=True)
        return
    category = await db.get_category(int(raw_id))
    if category is None:
        await callback.answer("Категория не найдена", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_price)
    await state.update_data(category_id=category.id)
    if callback.message is not None:
        await callback.message.edit_text(
            f"<b>{escape(category.name)}</b>\n\n"
            f"Текущая закупочная цена: {format_money(category.purchase_price)}\n\n"
            f"Введите новую закупочную цену за 1 шт. (в {config.currency}):"
        )
    await callback.answer()


@router.message(AdminStates.waiting_price, IsAdmin(), F.text)
async def save_price(message: Message, state: FSMContext) -> None:
    price = parse_amount(message.text)
    if price is None:
        await message.answer("Нужна сумма, например 3,20. Попробуйте еще раз:")
        return
    data = await state.get_data()
    category_id = int(data["category_id"])
    category = await db.get_category(category_id)
    if category is None:
        await state.clear()
        await message.answer("Категория не найдена.", reply_markup=admin_menu())
        return
    await db.set_purchase_price(category_id, price)
    await state.clear()
    await message.answer(
        f"✅ {escape(category.name)}: закупочная цена — {format_money(price)}",
        reply_markup=admin_menu(),
    )


# --------------------------------------------------------- новая категория


@router.callback_query(F.data == CB_CATEGORY_ADD, IsAdmin())
async def add_category_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_category_name)
    if callback.message is not None:
        await callback.message.edit_text(
            "Введите название новой категории (например GEEK BAR):"
        )
    await callback.answer()


@router.message(AdminStates.waiting_category_name, IsAdmin(), F.text)
async def add_category_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 64:
        await message.answer("Название должно быть от 1 до 64 символов:")
        return
    if await db.get_category_by_name(name):
        await state.clear()
        await message.answer(
            f"Категория «{escape(name)}» уже существует.", reply_markup=admin_menu()
        )
        return
    await state.update_data(new_category_name=name)
    await state.set_state(AdminStates.waiting_category_price)
    await message.answer(
        f"<b>{escape(name)}</b>\n\n"
        f"Введите закупочную цену за 1 шт. (в {config.currency}):",
        reply_markup=cancel_menu(),
    )


@router.message(AdminStates.waiting_category_price, IsAdmin(), F.text)
async def add_category_price(message: Message, state: FSMContext) -> None:
    price = parse_amount(message.text)
    if price is None:
        await message.answer("Нужна сумма, например 3,20. Попробуйте еще раз:")
        return
    await state.update_data(new_category_price=price)
    await state.set_state(AdminStates.waiting_category_is_liquid)
    await message.answer(
        "Это жидкость? Жидкости участвуют в расчете UPD.",
        reply_markup=liquid_menu(),
    )


@router.callback_query(
    AdminStates.waiting_category_is_liquid,
    F.data.startswith(CB_LIQUID_PREFIX),
    IsAdmin(),
)
async def add_category_finish(callback: CallbackQuery, state: FSMContext) -> None:
    is_liquid = (callback.data or "").endswith("1")
    data = await state.get_data()
    name = data["new_category_name"]
    price = float(data["new_category_price"])
    if await db.get_category_by_name(name):
        await state.clear()
        await callback.answer("Категория уже существует", show_alert=True)
        return
    await db.add_category(name=name, purchase_price=price, is_liquid=is_liquid)
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            f"✅ Категория добавлена\n\n"
            f"Название: <b>{escape(name)}</b>\n"
            f"Закупочная цена: {format_money(price)}\n"
            f"Жидкость: {'да' if is_liquid else 'нет'}",
            reply_markup=back_menu(),
        )
    await callback.answer("Категория появится в следующем отчете")


# ----------------------------------------------------------------- города


@router.callback_query(F.data == CB_CITIES, IsAdmin())
async def show_cities(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    cities = await db.get_cities(only_active=False)
    if callback.message is not None:
        await callback.message.edit_text(
            render_cities(cities), reply_markup=cities_menu(cities)
        )
    await callback.answer()


@router.callback_query(F.data == CB_CITY_ADD, IsAdmin())
async def add_city_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminStates.waiting_city_name)
    if callback.message is not None:
        await callback.message.edit_text("Введите название города:")
    await callback.answer()


@router.message(AdminStates.waiting_city_name, IsAdmin(), F.text)
async def add_city_finish(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name or len(name) > 64:
        await message.answer("Название должно быть от 1 до 64 символов:")
        return
    if await db.get_city_by_name(name):
        await state.clear()
        await message.answer(
            f"Город «{escape(name)}» уже существует.", reply_markup=admin_menu()
        )
        return
    await db.add_city(name)
    await state.clear()
    cities = await db.get_cities(only_active=False)
    await message.answer(
        f"✅ Город «{escape(name)}» добавлен.\n\n" + render_cities(cities),
        reply_markup=cities_menu(cities),
    )


@router.callback_query(F.data.startswith(CB_CITY_TOGGLE), IsAdmin())
async def toggle_city(callback: CallbackQuery) -> None:
    raw_id = (callback.data or "")[len(CB_CITY_TOGGLE) :]
    if not raw_id.isdigit():
        await callback.answer("Некорректный город", show_alert=True)
        return
    city = await db.get_city(int(raw_id))
    if city is None:
        await callback.answer("Город не найден", show_alert=True)
        return
    await db.set_city_active(city.id, not city.active)
    cities = await db.get_cities(only_active=False)
    if callback.message is not None:
        await callback.message.edit_text(
            render_cities(cities), reply_markup=cities_menu(cities)
        )
    await callback.answer(
        f"{city.name}: {'выключен' if city.active else 'включен'}"
    )


# ------------------------------------------------------- сохраненные отчеты


@router.callback_query(F.data == CB_REPORTS, IsAdmin())
async def show_reports(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    reports = await db.list_reports(limit=REPORTS_LIMIT)
    if callback.message is None:
        await callback.answer()
        return
    if not reports:
        await callback.message.edit_text(
            "Сохраненных отчетов пока нет.", reply_markup=back_menu()
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        render_reports_list(reports, "Последние отчеты"),
        reply_markup=reports_menu(reports),
    )
    await callback.answer()


@router.callback_query(F.data.startswith(CB_REPORT_PREFIX), IsAdmin())
async def show_report(callback: CallbackQuery) -> None:
    raw_id = (callback.data or "")[len(CB_REPORT_PREFIX) :]
    if not raw_id.isdigit():
        await callback.answer("Некорректный отчет", show_alert=True)
        return
    report = await db.get_report(int(raw_id))
    if report is None:
        await callback.answer("Отчет не найден", show_alert=True)
        return
    summary = summary_from_report(report)
    if callback.message is not None:
        await callback.message.answer(
            render_full_report(summary, f"ID {report.employee_telegram_id}"),
            reply_markup=back_menu(),
        )
    await callback.answer()
