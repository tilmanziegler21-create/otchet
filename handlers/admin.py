"""Админ-панель: закупочные цены, категории, сохраненные отчеты.

Все хендлеры закрыты фильтром IsAdmin — работник сюда не попадет.
"""

from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
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
    CB_CITY_CARD,
    CB_CITY_SALARY,
    CB_CITY_TOGGLE,
    CB_CLOSE,
    CB_GROUP_PREFIX,
    CB_MENU,
    CB_CITY_PLAN,
    CB_PERIOD,
    CB_PERIOD_CITY,
    CB_PICK_PREFIX,
    CB_PLAN_MONTH,
    CB_PRICE_EDIT,
    CB_PRICE_SET,
    CB_PRICES,
    CB_REPORT_PREFIX,
    CB_REPORTS,
    CB_SALARY_KIND,
    admin_menu,
    back_menu,
    categories_menu,
    cities_menu,
    city_card_menu,
    group_menu,
    period_cities_menu,
    period_menu,
    plan_months_menu,
    reports_menu,
    salary_kind_menu,
)
from keyboards.employee import BTN_ADMIN_PANEL, cancel_menu
from services.backup import send_backup
from services.calculations import PERIOD_MONTH, PERIOD_WEEK
from services.report_builder import (
    render_cities,
    render_city_card,
    render_full_report,
    render_period_report,
    render_plans,
    render_prices,
    render_reports_list,
)
from services.report_service import (
    period_bounds,
    summary_for_period,
    summary_for_report,
)
from utils import dates
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
    waiting_category_group = State()
    waiting_city_name = State()
    waiting_salary_value = State()
    waiting_plan_value = State()


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


@router.message(Command("backup"), IsAdmin())
async def cmd_backup(message: Message, state: FSMContext, bot: Bot) -> None:
    """Копия базы по требованию — на случай переезда или рискованных правок."""
    await state.clear()
    if not await send_backup(bot, chat_ids=(message.chat.id,)):
        await message.answer("Не удалось снять копию базы, смотрите логи.")


@router.message(Command("backup"), IsNotAdmin())
async def cmd_backup_denied(message: Message) -> None:
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
    await state.set_state(AdminStates.waiting_category_group)
    await message.answer(
        "В какую группу добавить позицию?\n\n"
        "Клиентов и UPD бот спрашивает только по жидкостям и электронкам.",
        reply_markup=group_menu(),
    )


@router.callback_query(
    AdminStates.waiting_category_group,
    F.data.startswith(CB_GROUP_PREFIX),
    IsAdmin(),
)
async def add_category_finish(callback: CallbackQuery, state: FSMContext) -> None:
    group_key = (callback.data or "")[len(CB_GROUP_PREFIX) :]
    if group_key not in db.GROUP_TITLES:
        await callback.answer("Неизвестная группа", show_alert=True)
        return
    data = await state.get_data()
    name = data["new_category_name"]
    price = float(data["new_category_price"])
    if await db.get_category_by_name(name):
        await state.clear()
        await callback.answer("Категория уже существует", show_alert=True)
        return
    await db.add_category(name=name, purchase_price=price, group_key=group_key)
    await state.clear()
    if callback.message is not None:
        await callback.message.edit_text(
            f"✅ Позиция добавлена\n\n"
            f"Название: <b>{escape(name)}</b>\n"
            f"Закупочная цена: {format_money(price)}\n"
            f"Группа: {db.GROUP_TITLES[group_key]}",
            reply_markup=back_menu(),
        )
    await callback.answer("Позиция появится в следующем отчете")


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


async def _resolve_city(callback: CallbackQuery, prefix: str) -> db.City | None:
    raw_id = (callback.data or "")[len(prefix) :]
    if not raw_id.isdigit():
        await callback.answer("Некорректный город", show_alert=True)
        return None
    city = await db.get_city(int(raw_id))
    if city is None:
        await callback.answer("Город не найден", show_alert=True)
        return None
    return city


async def _city_card_text(city: db.City) -> str:
    month = dates.month_key(dates.today())
    plan = await db.get_monthly_plan(city.id, month)
    return render_city_card(city, plan=plan, plan_month=month)


@router.callback_query(F.data.startswith(CB_CITY_CARD), IsAdmin())
async def show_city_card(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    city = await _resolve_city(callback, CB_CITY_CARD)
    if city is None:
        return
    if callback.message is not None:
        await callback.message.edit_text(
            await _city_card_text(city), reply_markup=city_card_menu(city)
        )
    await callback.answer()


@router.callback_query(F.data.startswith(CB_CITY_TOGGLE), IsAdmin())
async def toggle_city(callback: CallbackQuery) -> None:
    city = await _resolve_city(callback, CB_CITY_TOGGLE)
    if city is None:
        return
    await db.set_city_active(city.id, not city.active)
    updated = await db.get_city(city.id)
    if callback.message is not None and updated is not None:
        await callback.message.edit_text(
            await _city_card_text(updated), reply_markup=city_card_menu(updated)
        )
    await callback.answer(
        f"{city.name}: {'выключен' if city.active else 'включен'}"
    )


@router.callback_query(F.data.startswith(CB_CITY_SALARY), IsAdmin())
async def choose_salary_kind(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    city = await _resolve_city(callback, CB_CITY_SALARY)
    if city is None:
        return
    if callback.message is not None:
        await callback.message.edit_text(
            f"🏙 <b>{escape(city.name)}</b>\n\n"
            "Как считать «минус работникам» в этом городе?",
            reply_markup=salary_kind_menu(city.id),
        )
    await callback.answer()


@router.callback_query(F.data.startswith(CB_SALARY_KIND), IsAdmin())
async def ask_salary_value(callback: CallbackQuery, state: FSMContext) -> None:
    payload = (callback.data or "")[len(CB_SALARY_KIND) :]
    kind, _, raw_id = payload.partition(":")
    if kind not in db.SALARY_KINDS or not raw_id.isdigit():
        await callback.answer("Некорректный выбор", show_alert=True)
        return
    city = await db.get_city(int(raw_id))
    if city is None:
        await callback.answer("Город не найден", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_salary_value)
    await state.update_data(salary_city_id=city.id, salary_kind=kind)
    prompts = {
        db.SALARY_PERCENT: "Введите процент от общего оборота (например 30 или 27,5):",
        db.SALARY_FIXED: f"Введите сумму за день (в {config.currency}):",
        db.SALARY_MONTHLY: (
            f"Введите сумму за месяц (в {config.currency}), например 1300.\n\n"
            "В дневном отчете она делится на число дней этого месяца."
        ),
    }
    if callback.message is not None:
        await callback.message.edit_text(
            f"🏙 <b>{escape(city.name)}</b>\n\n{prompts[kind]}"
        )
    await callback.answer()


@router.message(AdminStates.waiting_salary_value, IsAdmin(), F.text)
async def save_salary_value(message: Message, state: FSMContext) -> None:
    value = parse_amount(message.text)
    data = await state.get_data()
    kind = data["salary_kind"]
    if value is None or (kind == db.SALARY_PERCENT and value > 100):
        hint = (
            "Нужен процент от 0 до 100, например 30 или 27,5:"
            if kind == db.SALARY_PERCENT
            else "Нужна сумма, например 50 или 47,50:"
        )
        await message.answer(hint)
        return

    city_id = int(data["salary_city_id"])
    await db.set_city_salary(city_id, kind, value)
    await state.clear()
    city = await db.get_city(city_id)
    if city is None:
        await message.answer("Город не найден.", reply_markup=admin_menu())
        return
    await message.answer(
        "✅ Ставка сохранена.\n\n" + await _city_card_text(city),
        reply_markup=city_card_menu(city),
    )


# --------------------------------------------------------- план на месяц


async def _plan_months(city_id: int) -> list[tuple[str, float]]:
    """Прошлый, текущий и следующий месяц с текущими планами."""
    today = dates.today()
    months = [dates.month_key(dates.shift_month(today, shift)) for shift in (-1, 0, 1)]
    return [(month, await db.get_monthly_plan(city_id, month)) for month in months]


@router.callback_query(F.data.startswith(CB_CITY_PLAN), IsAdmin())
async def show_plans(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    city = await _resolve_city(callback, CB_CITY_PLAN)
    if city is None:
        return
    months = await _plan_months(city.id)
    if callback.message is not None:
        await callback.message.edit_text(
            render_plans(city, months),
            reply_markup=plan_months_menu(city.id, months),
        )
    await callback.answer()


@router.callback_query(F.data.startswith(CB_PLAN_MONTH), IsAdmin())
async def ask_plan_value(callback: CallbackQuery, state: FSMContext) -> None:
    payload = (callback.data or "")[len(CB_PLAN_MONTH) :]
    month, _, raw_id = payload.partition(":")
    if not raw_id.isdigit() or len(month) != 7:
        await callback.answer("Некорректный выбор", show_alert=True)
        return
    city = await db.get_city(int(raw_id))
    if city is None:
        await callback.answer("Город не найден", show_alert=True)
        return

    await state.set_state(AdminStates.waiting_plan_value)
    await state.update_data(plan_city_id=city.id, plan_month=month)
    if callback.message is not None:
        await callback.message.edit_text(
            f"🎯 <b>{escape(city.name)}</b>, {dates.format_month(month)}\n\n"
            f"Введите план по обороту за месяц (в {config.currency}).\n"
            "0 — убрать план, тогда бонус за перевыполнение не начисляется."
        )
    await callback.answer()


@router.message(AdminStates.waiting_plan_value, IsAdmin(), F.text)
async def save_plan_value(message: Message, state: FSMContext) -> None:
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer("Нужна сумма, например 12000. Попробуйте еще раз:")
        return
    data = await state.get_data()
    city_id = int(data["plan_city_id"])
    month = data["plan_month"]
    await db.set_monthly_plan(city_id, month, amount)
    await state.clear()
    city = await db.get_city(city_id)
    if city is None:
        await message.answer("Город не найден.", reply_markup=admin_menu())
        return
    months = await _plan_months(city.id)
    saved = format_money(amount) if amount > 0 else "убран"
    await message.answer(
        f"✅ План на {dates.format_month(month)}: {saved}\n\n"
        + render_plans(city, months),
        reply_markup=plan_months_menu(city.id, months),
    )


# ------------------------------------------- сводки за неделю и за месяц


PERIOD_LABELS = {
    PERIOD_WEEK: {0: "Текущая неделя", -1: "Прошлая неделя", -2: "Позапрошлая неделя"},
    PERIOD_MONTH: {0: "Текущий месяц", -1: "Прошлый месяц", -2: "Позапрошлый месяц"},
}


def _period_buttons(kind: str) -> list[tuple[int, str]]:
    """Три периода с датами на кнопках: 'Прошлая неделя · 25.08–31.08'."""
    buttons = []
    for offset, label in PERIOD_LABELS[kind].items():
        start, end = period_bounds(kind, offset)
        if kind == PERIOD_WEEK:
            period = dates.format_range(start, end)
        else:
            period = dates.format_month(dates.month_key(start))
        buttons.append((offset, f"{label} · {period}"))
    return buttons


async def _ask_period_city(target: Message | CallbackQuery, kind: str) -> None:
    cities = await db.get_cities()
    kind_name = "неделю" if kind == PERIOD_WEEK else "месяц"
    text = f"Выберите город для отчета за {kind_name}:"
    if not cities:
        text = "Городов пока нет — сначала добавьте город в «🏙 Города»."
    markup = period_cities_menu(kind, cities) if cities else back_menu()
    if isinstance(target, CallbackQuery):
        if target.message is not None:
            await target.message.edit_text(text, reply_markup=markup)
        await target.answer()
    else:
        await target.answer(text, reply_markup=markup)


@router.message(Command("week"), IsAdmin())
async def cmd_week(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _ask_period_city(message, PERIOD_WEEK)


@router.message(Command("month"), IsAdmin())
async def cmd_month(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _ask_period_city(message, PERIOD_MONTH)


@router.message(Command("week", "month"), IsNotAdmin())
async def cmd_period_denied(message: Message) -> None:
    await message.answer("Команда недоступна.")


@router.callback_query(F.data.startswith(CB_PERIOD_CITY), IsAdmin())
async def choose_period_city(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    kind = (callback.data or "")[len(CB_PERIOD_CITY) :]
    if kind not in PERIOD_LABELS:
        await callback.answer("Некорректный выбор", show_alert=True)
        return
    await _ask_period_city(callback, kind)


@router.callback_query(F.data.startswith(CB_PERIOD), IsAdmin())
async def show_period_report(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    kind, _, rest = (callback.data or "")[len(CB_PERIOD) :].partition(":")
    raw_offset, _, raw_city = rest.partition(":")
    if kind not in PERIOD_LABELS or not raw_city.isdigit():
        await callback.answer("Некорректный выбор", show_alert=True)
        return
    city = await db.get_city(int(raw_city))
    if city is None:
        await callback.answer("Город не найден", show_alert=True)
        return

    offset = int(raw_offset)
    summary = await summary_for_period(kind, offset, city.id, city_name=city.name)
    if callback.message is not None:
        await callback.message.edit_text(
            render_period_report(summary),
            reply_markup=period_menu(kind, city.id, _period_buttons(kind)),
        )
    await callback.answer()


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
    summary = await summary_for_report(report)
    if callback.message is not None:
        await callback.message.answer(
            render_full_report(summary, f"ID {report.employee_telegram_id}"),
            reply_markup=back_menu(),
        )
    await callback.answer()
