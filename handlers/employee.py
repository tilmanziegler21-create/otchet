"""Сценарий работника: новый отчет по категориям -> предпросмотр -> сохранение."""

from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, User

import database as db
from config import config
from keyboards.employee import (
    BTN_NEW_REPORT,
    BTN_TODAY_DATE_PREFIX,
    CB_BACK,
    CB_CONFIRM,
    CB_EDIT,
    CB_EDIT_CATEGORY,
    CB_EDIT_CUSTOMERS,
    cancel_menu,
    date_menu,
    edit_menu,
    main_menu,
    preview_menu,
)
from services.calculations import CategoryLine, build_summary
from services.notifications import send_report_to_admins
from services.report_builder import render_employee_result, render_preview
from utils import dates
from utils.formatting import parse_amount, parse_int

router = Router(name="employee")


class NewReport(StatesGroup):
    waiting_date = State()
    waiting_quantity = State()
    waiting_revenue = State()
    waiting_customers = State()
    preview = State()
    choose_edit = State()


def _employee_label(user: User) -> str:
    parts = [user.full_name]
    if user.username:
        parts.append(f"@{user.username}")
    parts.append(f"ID {user.id}")
    return " / ".join(parts)


async def _ask_quantity(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    categories = data["categories"]
    index = data["index"]
    category = categories[index]
    position = "" if data.get("edit_target") else f" ({index + 1}/{len(categories)})"
    await state.set_state(NewReport.waiting_quantity)
    await message.answer(
        f"<b>{escape(category['name'])}</b>{position}\n\n"
        "Введите количество проданных штук:",
        reply_markup=cancel_menu(),
    )


async def _ask_revenue(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    category = data["categories"][data["index"]]
    await state.set_state(NewReport.waiting_revenue)
    await message.answer(
        f"<b>{escape(category['name'])}</b>\n\n"
        f"Введите общую выручку по {escape(category['name'])} "
        f"(в {config.currency}):",
        reply_markup=cancel_menu(),
    )


async def _ask_customers(message: Message, state: FSMContext) -> None:
    await state.set_state(NewReport.waiting_customers)
    await message.answer(
        "Сколько сегодня было покупателей?", reply_markup=cancel_menu()
    )


async def _show_preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data(edit_target=None)
    rows = [
        (
            category["name"],
            data["entries"][str(index)]["quantity"],
            data["entries"][str(index)]["revenue"],
        )
        for index, category in enumerate(data["categories"])
    ]
    text = render_preview(
        dates.from_db(data["date"]), rows, int(data["customers_count"])
    )
    await state.set_state(NewReport.preview)
    await message.answer(text, reply_markup=preview_menu())


# ----------------------------------------------------------------- запуск


@router.message(F.text == BTN_NEW_REPORT)
async def start_new_report(message: Message, state: FSMContext) -> None:
    categories = await db.get_categories(only_active=True)
    if not categories:
        await message.answer(
            "Категории пока не настроены. Сообщите администратору."
        )
        return
    await state.clear()
    await state.set_state(NewReport.waiting_date)
    await state.update_data(
        categories=[
            {"id": c.id, "name": c.name, "is_liquid": c.is_liquid} for c in categories
        ],
        entries={},
        index=0,
        edit_target=None,
    )
    await message.answer(
        "За какую дату отчет?\n\n"
        "Нажмите кнопку с сегодняшней датой или введите дату вручную "
        "в формате ДД.ММ или ДД.ММ.ГГГГ.",
        reply_markup=date_menu(),
    )


@router.message(NewReport.waiting_date, F.text)
async def process_date(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text.startswith(BTN_TODAY_DATE_PREFIX):
        report_date = dates.today()
    else:
        report_date = dates.parse_user_date(text)
    if report_date is None:
        await message.answer(
            "Не понял дату. Введите ее в формате ДД.ММ или ДД.ММ.ГГГГ.",
            reply_markup=date_menu(),
        )
        return

    await state.update_data(date=dates.to_db(report_date))
    existing = await db.count_reports_by_date(dates.to_db(report_date))
    if existing:
        await message.answer(
            f"⚠️ Отчет за {dates.format_full(report_date)} уже есть в базе. "
            "Новый отчет будет сохранен отдельно."
        )
    await message.answer(f"Дата отчета: {dates.format_full(report_date)}")
    await _ask_quantity(message, state)


@router.message(NewReport.waiting_quantity, F.text)
async def process_quantity(message: Message, state: FSMContext) -> None:
    quantity = parse_int(message.text)
    if quantity is None:
        await message.answer(
            "Нужно целое число штук (например 43). Попробуйте еще раз:",
            reply_markup=cancel_menu(),
        )
        return
    data = await state.get_data()
    entries = dict(data["entries"])
    key = str(data["index"])
    entry = dict(entries.get(key, {}))
    entry["quantity"] = quantity
    entries[key] = entry
    await state.update_data(entries=entries)
    await _ask_revenue(message, state)


@router.message(NewReport.waiting_revenue, F.text)
async def process_revenue(message: Message, state: FSMContext) -> None:
    revenue = parse_amount(message.text)
    if revenue is None:
        await message.answer(
            "Нужна сумма выручки (например 571 или 571,50). Попробуйте еще раз:",
            reply_markup=cancel_menu(),
        )
        return

    data = await state.get_data()
    entries = dict(data["entries"])
    key = str(data["index"])
    entry = dict(entries.get(key, {}))
    entry["revenue"] = revenue
    entries[key] = entry
    await state.update_data(entries=entries)

    if data.get("edit_target"):
        await _show_preview(message, state)
        return

    next_index = data["index"] + 1
    if next_index < len(data["categories"]):
        await state.update_data(index=next_index)
        await _ask_quantity(message, state)
    else:
        await _ask_customers(message, state)


@router.message(NewReport.waiting_customers, F.text)
async def process_customers(message: Message, state: FSMContext) -> None:
    customers = parse_int(message.text)
    if customers is None:
        await message.answer(
            "Нужно целое число покупателей (например 32). Попробуйте еще раз:",
            reply_markup=cancel_menu(),
        )
        return
    await state.update_data(customers_count=customers)
    await _show_preview(message, state)


# ------------------------------------------------------- предпросмотр


@router.callback_query(NewReport.preview, F.data == CB_CONFIRM)
async def confirm_report(
    callback: CallbackQuery, state: FSMContext, bot: Bot
) -> None:
    if callback.from_user is None:
        await callback.answer()
        return

    data = await state.get_data()
    report_date = data["date"]
    customers_count = int(data["customers_count"])
    entries = data["entries"]

    items: list[tuple[int, int, float, float]] = []
    lines: list[CategoryLine] = []
    for index, category in enumerate(data["categories"]):
        entry = entries[str(index)]
        quantity = int(entry["quantity"])
        revenue = float(entry["revenue"])
        fresh = await db.get_category(category["id"])
        purchase_price = fresh.purchase_price if fresh else 0.0
        is_liquid = fresh.is_liquid if fresh else bool(category["is_liquid"])
        items.append((category["id"], quantity, revenue, purchase_price))
        lines.append(
            CategoryLine(
                category_id=category["id"],
                name=fresh.name if fresh else category["name"],
                is_liquid=is_liquid,
                quantity=quantity,
                revenue=revenue,
                purchase_price=purchase_price,
            )
        )

    report_id = await db.save_report(
        report_date=report_date,
        employee_telegram_id=callback.from_user.id,
        customers_count=customers_count,
        items=items,
    )
    summary = build_summary(
        report_date=dates.from_db(report_date),
        customers_count=customers_count,
        lines=lines,
        report_id=report_id,
        employee_telegram_id=callback.from_user.id,
    )

    await state.clear()
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Сохранено")

    is_admin = config.is_admin(callback.from_user.id)
    await bot.send_message(
        callback.from_user.id,
        render_employee_result(summary),
        reply_markup=main_menu(is_admin),
    )
    await send_report_to_admins(
        bot,
        summary,
        employee_label=_employee_label(callback.from_user),
    )


@router.callback_query(NewReport.preview, F.data == CB_EDIT)
async def choose_edit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    names = [category["name"] for category in data["categories"]]
    await state.set_state(NewReport.choose_edit)
    if callback.message is not None:
        await callback.message.edit_text(
            "Что нужно исправить?", reply_markup=edit_menu(names)
        )
    await callback.answer()


@router.callback_query(NewReport.choose_edit, F.data.startswith(CB_EDIT_CATEGORY))
async def edit_category(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        index = int((callback.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        await callback.answer("Не удалось определить категорию", show_alert=True)
        return
    if not 0 <= index < len(data["categories"]):
        await callback.answer("Категория не найдена", show_alert=True)
        return

    await state.update_data(index=index, edit_target="category")
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _ask_quantity(callback.message, state)
    await callback.answer()


@router.callback_query(NewReport.choose_edit, F.data == CB_EDIT_CUSTOMERS)
async def edit_customers(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(edit_target="customers")
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _ask_customers(callback.message, state)
    await callback.answer()


@router.callback_query(NewReport.choose_edit, F.data == CB_BACK)
async def back_to_preview(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _show_preview(callback.message, state)
    await callback.answer()


# ------------------------------------------------------------ подсказки


@router.message(NewReport.waiting_date)
@router.message(NewReport.waiting_quantity)
@router.message(NewReport.waiting_revenue)
@router.message(NewReport.waiting_customers)
async def wrong_input_type(message: Message) -> None:
    await message.answer("Отправьте ответ текстом или нажмите «❌ Отмена».")


@router.message(NewReport.preview)
@router.message(NewReport.choose_edit)
async def use_buttons(message: Message) -> None:
    await message.answer("Воспользуйтесь кнопками под сообщением с отчетом.")
