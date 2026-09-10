"""Сценарий работника: новый отчет по категориям -> предпросмотр -> сохранение."""

from __future__ import annotations

from html import escape
from typing import Sequence

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
    CB_CITY,
    CB_CONFIRM,
    CB_EDIT,
    CB_EDIT_CATEGORY,
    CB_EDIT_CITY,
    CB_EDIT_CUSTOMERS,
    CB_EDIT_ITEMS,
    CB_EDIT_OUTREACH,
    CB_PICK,
    CB_PICK_DONE,
    CB_PICK_NONE,
    cancel_menu,
    cities_menu,
    date_menu,
    edit_menu,
    main_menu,
    picker_menu,
    preview_menu,
)
from services.calculations import CategoryLine, build_summary
from services.notifications import send_report_to_admins
from services.report_service import resolve_bonus
from services.report_builder import render_employee_result, render_preview
from utils import dates
from utils.formatting import parse_amount, parse_int

router = Router(name="employee")


class NewReport(StatesGroup):
    waiting_city = State()
    waiting_date = State()
    picking = State()
    waiting_quantity = State()
    waiting_revenue = State()
    waiting_category_customers = State()
    waiting_customers = State()
    waiting_touches = State()
    waiting_replies = State()
    waiting_purchases = State()
    waiting_extra_revenue = State()
    preview = State()
    choose_edit = State()


def _employee_label(user: User) -> str:
    parts = [user.full_name]
    if user.username:
        parts.append(f"@{user.username}")
    parts.append(f"ID {user.id}")
    return " / ".join(parts)


async def _ask_city(message: Message, state: FSMContext) -> bool:
    """Показывает список городов. False — городов нет, отчет начать нельзя."""
    cities = await db.get_cities(only_active=True)
    if not cities:
        await message.answer(
            "Города пока не настроены — обратитесь к администратору.",
            reply_markup=main_menu(config.is_admin(message.chat.id)),
        )
        return False
    await state.set_state(NewReport.waiting_city)
    await message.answer("Выберите город:", reply_markup=cities_menu(cities))
    return True


async def _ask_date(message: Message, state: FSMContext) -> None:
    await state.set_state(NewReport.waiting_date)
    await message.answer(
        "За какую дату отчет?\n\n"
        "Нажмите кнопку с сегодняшней датой или введите дату вручную "
        "в формате ДД.ММ или ДД.ММ.ГГГГ.",
        reply_markup=date_menu(),
    )


async def _ask_picker(message: Message, state: FSMContext, edit: bool = False) -> None:
    """Показывает позиции текущей группы с галочками."""
    data = await state.get_data()
    group = data["catalog"][data["group_index"]]
    picked = [item["id"] for item in group["items"] if item["id"] in data["picked"]]
    text = (
        f"<b>{escape(group['title'])}</b> "
        f"({data['group_index'] + 1}/{len(data['catalog'])})\n\n"
        "Отметьте, что продавалось сегодня:"
    )
    markup = picker_menu([(item["id"], item["name"]) for item in group["items"]], picked)
    await state.set_state(NewReport.picking)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def _start_filling(message: Message, state: FSMContext) -> None:
    """Выбор закончен: собираем отмеченные позиции и спрашиваем по ним цифры."""
    data = await state.get_data()
    picked = set(data["picked"])
    categories = [
        item
        for group in data["catalog"]
        for item in group["items"]
        if item["id"] in picked
    ]
    if not categories:
        await message.answer(
            "Ничего не отмечено — отчет пустой. Начнем выбор заново."
        )
        await state.update_data(group_index=0)
        await _ask_picker(message, state)
        return

    # При правке списка уже введенные цифры сохраняем — они привязаны к позиции.
    filled = {
        category["id"]: data["entries"][str(index)]
        for index, category in enumerate(data.get("categories", []))
        if str(index) in data["entries"]
    }
    entries = {
        str(index): filled[category["id"]]
        for index, category in enumerate(categories)
        if category["id"] in filled
    }
    await state.update_data(categories=categories, entries=entries)

    names = ", ".join(category["name"] for category in categories)
    await message.answer(f"Отмечено позиций: {len(categories)}\n{escape(names)}")

    missing = [index for index in range(len(categories)) if str(index) not in entries]
    if not missing:
        await state.update_data(index=0)
        await _show_preview(message, state)
        return
    await state.update_data(index=missing[0], edit_target=None)
    await _ask_quantity(message, state)


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


async def _ask_category_customers(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    category = data["categories"][data["index"]]
    await state.set_state(NewReport.waiting_category_customers)
    await message.answer(
        f"<b>{escape(category['name'])}</b>\n\n"
        f"Сколько клиентов купили {escape(category['name'])}?",
        reply_markup=cancel_menu(),
    )


async def _ask_customers(message: Message, state: FSMContext) -> None:
    await state.set_state(NewReport.waiting_customers)
    await message.answer(
        "Сколько всего сегодня было покупателей?", reply_markup=cancel_menu()
    )


async def _ask_touches(message: Message, state: FSMContext) -> None:
    await state.set_state(NewReport.waiting_touches)
    await message.answer(
        "Сколько было рассылок (касаний) за день?\n\n"
        "Если рассылок не было — отправьте 0.",
        reply_markup=cancel_menu(),
    )


async def _ask_replies(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(NewReport.waiting_replies)
    await message.answer(
        f"Касаний — {data['touches']}.\n\nСколько из них ответили?",
        reply_markup=cancel_menu(),
    )


async def _ask_purchases(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(NewReport.waiting_purchases)
    await message.answer(
        f"Ответили — {data['replies']}.\n\nСколько из них перешли к покупке?",
        reply_markup=cancel_menu(),
    )


async def _ask_extra_revenue(message: Message, state: FSMContext) -> None:
    await state.set_state(NewReport.waiting_extra_revenue)
    await message.answer(
        f"Какой доп оборот создали рассылки (в {config.currency})?",
        reply_markup=cancel_menu(),
    )


async def _next_step(message: Message, state: FSMContext) -> None:
    """Категория заполнена: следующая категория, покупатели или предпросмотр."""
    data = await state.get_data()
    if data.get("edit_target"):
        await _show_preview(message, state)
        return
    # После правки списка позиций часть цифр уже введена — их не переспрашиваем.
    next_index = next(
        (
            index
            for index in range(data["index"] + 1, len(data["categories"]))
            if str(index) not in data["entries"]
        ),
        None,
    )
    if next_index is not None:
        await state.update_data(index=next_index)
        await _ask_quantity(message, state)
    elif "customers_count" in data:
        await _show_preview(message, state)
    else:
        await _ask_customers(message, state)


async def _show_preview(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.update_data(edit_target=None)
    rows = [
        (
            category["group_key"],
            category["name"],
            data["entries"][str(index)]["quantity"],
            data["entries"][str(index)]["revenue"],
            data["entries"][str(index)]["customers"]
            if category["needs_customers"]
            else None,
        )
        for index, category in enumerate(data["categories"])
    ]
    text = render_preview(
        dates.from_db(data["date"]),
        rows,
        int(data["customers_count"]),
        city_name=data.get("city_name"),
        outreach=(
            int(data.get("touches", 0)),
            int(data.get("replies", 0)),
            int(data.get("purchases", 0)),
            float(data.get("extra_revenue", 0.0)),
        ),
    )
    await state.set_state(NewReport.preview)
    await message.answer(text, reply_markup=preview_menu())


# ----------------------------------------------------------------- запуск


def _build_catalog(categories: Sequence[db.Category]) -> list[dict]:
    """Раскладывает позиции по группам, пустые группы пропускаем."""
    catalog: list[dict] = []
    for group_key, title in db.GROUP_TITLES.items():
        items = [
            {
                "id": category.id,
                "name": category.name,
                "is_liquid": category.is_liquid,
                "group_key": category.group_key,
                "needs_customers": category.needs_customers,
            }
            for category in categories
            if category.group_key == group_key
        ]
        if items:
            catalog.append({"key": group_key, "title": title, "items": items})
    return catalog


@router.message(F.text == BTN_NEW_REPORT)
async def start_new_report(message: Message, state: FSMContext) -> None:
    categories = await db.get_categories(only_active=True)
    if not categories:
        await message.answer(
            "Категории пока не настроены. Сообщите администратору."
        )
        return
    await state.clear()
    await state.update_data(
        catalog=_build_catalog(categories),
        picked=[],
        group_index=0,
        categories=[],
        entries={},
        index=0,
        edit_target=None,
    )
    await _ask_city(message, state)


@router.callback_query(NewReport.waiting_city, F.data.startswith(CB_CITY))
async def process_city(callback: CallbackQuery, state: FSMContext) -> None:
    raw_id = (callback.data or "")[len(CB_CITY) :]
    if not raw_id.isdigit():
        await callback.answer("Некорректный город", show_alert=True)
        return
    city = await db.get_city(int(raw_id))
    if city is None or not city.active:
        await callback.answer("Город недоступен", show_alert=True)
        return

    await state.update_data(city_id=city.id, city_name=city.name)
    data = await state.get_data()
    if callback.message is not None:
        await callback.message.edit_text(f"Город: <b>{escape(city.name)}</b>")
        if data.get("edit_target"):
            await _show_preview(callback.message, state)
        else:
            await _ask_date(callback.message, state)
    await callback.answer()


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
    data = await state.get_data()
    existing = await db.count_reports_by_date(
        dates.to_db(report_date), city_id=data.get("city_id")
    )
    if existing:
        city_label = data.get("city_name") or "этот город"
        await message.answer(
            f"⚠️ Отчет за {dates.format_full(report_date)} по {city_label} "
            "уже есть в базе. Новый отчет будет сохранен отдельно."
        )
    await message.answer(f"Дата отчета: {dates.format_full(report_date)}")
    await _ask_picker(message, state)


# ------------------------------------------------------- выбор позиций


@router.callback_query(NewReport.picking, F.data == CB_PICK_DONE)
async def picker_done(callback: CallbackQuery, state: FSMContext) -> None:
    await _picker_next_group(callback, state)


@router.callback_query(NewReport.picking, F.data == CB_PICK_NONE)
async def picker_skip(callback: CallbackQuery, state: FSMContext) -> None:
    """Пропуск группы: снимаем отметки, если работник их уже поставил."""
    data = await state.get_data()
    group = data["catalog"][data["group_index"]]
    group_ids = {item["id"] for item in group["items"]}
    await state.update_data(
        picked=[item_id for item_id in data["picked"] if item_id not in group_ids]
    )
    await _picker_next_group(callback, state)


async def _picker_next_group(callback: CallbackQuery, state: FSMContext) -> None:
    """Следующая группа или переход к вводу цифр по отмеченным позициям."""
    data = await state.get_data()
    group = data["catalog"][data["group_index"]]
    chosen = [item["name"] for item in group["items"] if item["id"] in data["picked"]]
    if callback.message is not None:
        await callback.message.edit_text(
            f"<b>{escape(group['title'])}</b>: "
            + (escape(", ".join(chosen)) if chosen else "не продавалось")
        )

    next_index = data["group_index"] + 1
    await state.update_data(group_index=next_index)
    if callback.message is not None:
        if next_index < len(data["catalog"]):
            await _ask_picker(callback.message, state)
        else:
            await _start_filling(callback.message, state)
    await callback.answer()


@router.callback_query(NewReport.picking, F.data.startswith(CB_PICK))
async def picker_toggle(callback: CallbackQuery, state: FSMContext) -> None:
    raw_id = (callback.data or "")[len(CB_PICK) :]
    if not raw_id.isdigit():
        await callback.answer("Не понял позицию", show_alert=True)
        return

    item_id = int(raw_id)
    data = await state.get_data()
    picked = list(data["picked"])
    if item_id in picked:
        picked.remove(item_id)
    else:
        picked.append(item_id)
    await state.update_data(picked=picked)

    group = data["catalog"][data["group_index"]]
    if callback.message is not None:
        await callback.message.edit_reply_markup(
            reply_markup=picker_menu(
                [(item["id"], item["name"]) for item in group["items"]],
                [item["id"] for item in group["items"] if item["id"] in picked],
            )
        )
    await callback.answer()


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
    category_name = data["categories"][data["index"]]["name"]

    if quantity == 0:
        # Нечего продавать — ни выручку, ни клиентов не спрашиваем.
        entry["revenue"] = 0.0
        entry["customers"] = 0
        entries[key] = entry
        await state.update_data(entries=entries)
        await message.answer(
            f"{escape(category_name)}: продаж нет, выручку и клиентов не спрашиваю."
        )
        await _next_step(message, state)
        return

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

    if not data["categories"][data["index"]]["needs_customers"]:
        # По подам, картриджам и наборам UPD не считаем — клиентов не спрашиваем.
        entry["customers"] = 0
        entries[key] = entry
        await state.update_data(entries=entries)
        await _next_step(message, state)
        return
    await _ask_category_customers(message, state)


@router.message(NewReport.waiting_category_customers, F.text)
async def process_category_customers(message: Message, state: FSMContext) -> None:
    clients = parse_int(message.text)
    if clients is None:
        await message.answer(
            "Нужно целое число клиентов (например 28). Попробуйте еще раз:",
            reply_markup=cancel_menu(),
        )
        return

    data = await state.get_data()
    entries = dict(data["entries"])
    key = str(data["index"])
    entry = dict(entries.get(key, {}))
    if clients > int(entry["quantity"]):
        # Один клиент мог взять несколько штук, но не наоборот.
        await message.answer(
            f"Клиентов не может быть больше проданных штук "
            f"({entry['quantity']}). Введите число заново:",
            reply_markup=cancel_menu(),
        )
        return
    entry["customers"] = clients
    entries[key] = entry
    await state.update_data(entries=entries)
    await _next_step(message, state)


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
    data = await state.get_data()
    if data.get("edit_target"):
        await _show_preview(message, state)
        return
    await _ask_touches(message, state)


@router.message(NewReport.waiting_touches, F.text)
async def process_touches(message: Message, state: FSMContext) -> None:
    touches = parse_int(message.text)
    if touches is None:
        await message.answer(
            "Нужно целое число касаний (например 120). Попробуйте еще раз:",
            reply_markup=cancel_menu(),
        )
        return

    if touches == 0:
        # Рассылок не было — остальные вопросы не задаем.
        await state.update_data(
            touches=0, replies=0, purchases=0, extra_revenue=0.0
        )
        await message.answer("Рассылок не было, остальное не спрашиваю.")
        await _show_preview(message, state)
        return

    await state.update_data(touches=touches)
    await _ask_replies(message, state)


@router.message(NewReport.waiting_replies, F.text)
async def process_replies(message: Message, state: FSMContext) -> None:
    replies = parse_int(message.text)
    if replies is None:
        await message.answer(
            "Нужно целое число ответивших (например 30). Попробуйте еще раз:",
            reply_markup=cancel_menu(),
        )
        return
    data = await state.get_data()
    if replies > int(data["touches"]):
        await message.answer(
            f"Ответивших не может быть больше касаний ({data['touches']}). "
            "Введите число заново:",
            reply_markup=cancel_menu(),
        )
        return
    await state.update_data(replies=replies)
    await _ask_purchases(message, state)


@router.message(NewReport.waiting_purchases, F.text)
async def process_purchases(message: Message, state: FSMContext) -> None:
    purchases = parse_int(message.text)
    if purchases is None:
        await message.answer(
            "Нужно целое число покупок (например 12). Попробуйте еще раз:",
            reply_markup=cancel_menu(),
        )
        return
    data = await state.get_data()
    if purchases > int(data["replies"]):
        await message.answer(
            f"Покупок не может быть больше ответивших ({data['replies']}). "
            "Введите число заново:",
            reply_markup=cancel_menu(),
        )
        return
    await state.update_data(purchases=purchases)
    await _ask_extra_revenue(message, state)


@router.message(NewReport.waiting_extra_revenue, F.text)
async def process_extra_revenue(message: Message, state: FSMContext) -> None:
    extra_revenue = parse_amount(message.text)
    if extra_revenue is None:
        await message.answer(
            "Нужна сумма доп оборота (например 340 или 340,50). "
            "Попробуйте еще раз:",
            reply_markup=cancel_menu(),
        )
        return
    await state.update_data(extra_revenue=extra_revenue)
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
    touches = int(data.get("touches", 0))
    replies = int(data.get("replies", 0))
    purchases = int(data.get("purchases", 0))
    extra_revenue = float(data.get("extra_revenue", 0.0))

    items: list[tuple[int, int, float, float, int]] = []
    lines: list[CategoryLine] = []
    for index, category in enumerate(data["categories"]):
        entry = entries[str(index)]
        quantity = int(entry["quantity"])
        revenue = float(entry["revenue"])
        clients = int(entry["customers"])
        fresh = await db.get_category(category["id"])
        purchase_price = fresh.purchase_price if fresh else 0.0
        is_liquid = fresh.is_liquid if fresh else bool(category["is_liquid"])
        group_key = fresh.group_key if fresh else category["group_key"]
        items.append((category["id"], quantity, revenue, purchase_price, clients))
        lines.append(
            CategoryLine(
                category_id=category["id"],
                name=fresh.name if fresh else category["name"],
                is_liquid=is_liquid,
                quantity=quantity,
                revenue=revenue,
                purchase_price=purchase_price,
                customers_count=clients,
                group_key=group_key,
            )
        )

    # Ставку работникам фиксируем на момент отчета — как и закупочные цены.
    city_id = data.get("city_id")
    city = await db.get_city(city_id) if city_id else None
    salary_kind = city.salary_kind if city else db.SALARY_PERCENT
    salary_value = city.salary_value if city else 0.0

    # Бонус за перевыполнение считаем от кассы месяца до этого отчета.
    day_revenue = sum(revenue for _, _, revenue, _, _ in items)
    bonus_context = await resolve_bonus(
        city_id, dates.from_db(report_date), day_revenue
    )

    report_id = await db.save_report(
        report_date=report_date,
        city_id=city_id,
        employee_telegram_id=callback.from_user.id,
        customers_count=customers_count,
        salary_kind=salary_kind,
        salary_value=salary_value,
        bonus=bonus_context.bonus,
        plan=bonus_context.plan,
        items=items,
        touches=touches,
        replies=replies,
        purchases=purchases,
        extra_revenue=extra_revenue,
    )
    summary = build_summary(
        report_date=dates.from_db(report_date),
        customers_count=customers_count,
        lines=lines,
        city_name=city.name if city else data.get("city_name"),
        salary_kind=salary_kind,
        salary_value=salary_value,
        bonus=bonus_context.bonus,
        plan=bonus_context.plan,
        month_revenue=bonus_context.month_revenue,
        touches=touches,
        replies=replies,
        purchases=purchases,
        extra_revenue=extra_revenue,
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


@router.callback_query(NewReport.choose_edit, F.data == CB_EDIT_ITEMS)
async def edit_items(callback: CallbackQuery, state: FSMContext) -> None:
    """Правка списка проданных позиций: заново проходим группы с галочками."""
    await state.update_data(group_index=0, edit_target=None)
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _ask_picker(callback.message, state)
    await callback.answer()


@router.callback_query(NewReport.choose_edit, F.data == CB_EDIT_CITY)
async def edit_city(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(edit_target="city")
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _ask_city(callback.message, state)
    await callback.answer()


@router.callback_query(NewReport.choose_edit, F.data == CB_EDIT_CUSTOMERS)
async def edit_customers(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(edit_target="customers")
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _ask_customers(callback.message, state)
    await callback.answer()


@router.callback_query(NewReport.choose_edit, F.data == CB_EDIT_OUTREACH)
async def edit_outreach(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(edit_target="outreach")
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=None)
        await _ask_touches(callback.message, state)
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
@router.message(NewReport.waiting_category_customers)
@router.message(NewReport.waiting_customers)
@router.message(NewReport.waiting_touches)
@router.message(NewReport.waiting_replies)
@router.message(NewReport.waiting_purchases)
@router.message(NewReport.waiting_extra_revenue)
async def wrong_input_type(message: Message) -> None:
    await message.answer("Отправьте ответ текстом или нажмите «❌ Отмена».")


@router.message(NewReport.waiting_city)
@router.message(NewReport.picking)
@router.message(NewReport.preview)
@router.message(NewReport.choose_edit)
async def use_buttons(message: Message) -> None:
    await message.answer("Воспользуйтесь кнопками под сообщением.")
