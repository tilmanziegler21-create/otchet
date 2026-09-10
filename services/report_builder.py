"""Сборка текстов: полный отчет для админа, безопасный — для работника."""

from __future__ import annotations

from datetime import date
from html import escape
from typing import Sequence

from database import (
    EXPENSE_FIXED,
    EXPENSE_MONTHLY,
    EXPENSE_NONE,
    GROUP_TITLES,
    SALARY_FIXED,
    SALARY_MONTHLY,
    Category,
    City,
    Payout,
    ReportBrief,
)
from services.calculations import (
    BONUS_SHARE,
    MANAGER_SHARE,
    PERIOD_WEEK,
    PeriodSummary,
    ReportSummary,
    SummaryTotals,
)
from services.pots import PotBalance
from utils import dates
from utils.formatting import format_amount, format_money, format_quantity, format_upd


def _percent_label(share: float) -> str:
    return f"{format_amount(share * 100, 2)}%"


def format_salary_rate(salary_kind: str, salary_value: float) -> str:
    """'30%', '50€ в день' или '1300€ в месяц' — как задана ставка города."""
    if salary_kind == SALARY_FIXED:
        return f"{format_money(salary_value)} в день"
    if salary_kind == SALARY_MONTHLY:
        return f"{format_money(salary_value)} в месяц"
    return f"{format_amount(salary_value, 2)}%"


def format_expense_rate(expense_kind: str, expense_value: float) -> str:
    """'нет', '80€ в день' или '300€ в месяц'."""
    if expense_kind == EXPENSE_FIXED:
        return f"{format_money(expense_value)} в день"
    if expense_kind == EXPENSE_MONTHLY:
        return f"{format_money(expense_value)} в месяц"
    return "нет"


def _header(
    report_date: date | str, city_name: str | None, full_date: bool = False
) -> str:
    """'01.09 · Рига' — город в шапке, чтобы отчеты точек не путались."""
    text = dates.format_full(report_date) if full_date else dates.format_short(report_date)
    if city_name:
        text += f" · {escape(city_name)}"
    return text


def _category_block(summary: SummaryTotals, line) -> str:
    """Блок одной позиции: клиенты и UPD — только там, где их спрашивали."""
    rows = [
        f"<b>{escape(line.name)}:</b>",
        "",
        f"Количество — {format_quantity(line.quantity)}",
        f"Выручка — {format_money(line.revenue)}",
    ]
    if line.shows_customers:
        rows.append(f"Клиентов — {line.customers_count}")
    rows.append(f"Средний чек — {format_money(line.average_check)}")
    if line.shows_customers:
        rows.append(f"UPD — {format_upd(line.upd)}")
    rows.append(f"Себестоимость — {format_money(line.cost)}")
    rows.append(f"Чистая прибыль — {format_money(summary.category_profit(line))}")
    return "\n".join(rows)


def _category_blocks(summary: SummaryTotals) -> list[str]:
    """Блоки по позициям (с заголовками групп), затем итог по жидкостям."""
    parts: list[str] = []
    current_group = None
    for line in summary.lines:
        if line.group_key != current_group:
            current_group = line.group_key
            title = GROUP_TITLES.get(current_group, current_group)
            parts.append(f"<b>— {title.upper()} —</b>")
        parts.append(_category_block(summary, line))
    parts.append(
        "<b>ВСЕ ЖИДКОСТИ:</b>\n\n"
        f"Количество — {format_quantity(summary.liquid_quantity)}\n"
        f"Выручка — {format_money(summary.liquid_revenue)}\n"
        f"Средний чек жидкости — {format_money(summary.liquid_average_check)}"
    )
    parts.append(
        f"Количество покупателей — {summary.customers_count}\n"
        f"UPD — {format_upd(summary.upd)}"
    )
    parts.append(_outreach_block(summary))
    return parts


def _outreach_block(summary: SummaryTotals) -> str:
    """Рассылки: касания, ответы, покупки, доп оборот и конверсии."""
    if not summary.touches:
        return "<b>РАССЫЛКИ:</b>\n\nРассылок не было."
    return (
        "<b>РАССЫЛКИ:</b>\n\n"
        f"Касаний — {summary.touches}\n"
        f"Ответили — {summary.replies} "
        f"({format_amount(summary.reply_rate, 2)}% от касаний)\n"
        f"Перешли к покупке — {summary.purchases} "
        f"({format_amount(summary.purchase_rate, 2)}% от ответивших)\n"
        f"Доп оборот — {format_money(summary.extra_revenue)} "
        "(уже в общей выручке)"
    )


def _outreach_line(summary: SummaryTotals) -> str:
    """Одна строка о рассылках — для безопасных сводок работника."""
    if not summary.touches:
        return "Рассылки: не было"
    return (
        f"Рассылки: касаний {summary.touches}, "
        f"ответили {summary.replies} ({format_amount(summary.reply_rate, 2)}%), "
        f"покупки {summary.purchases} "
        f"({format_amount(summary.purchase_rate, 2)}%), "
        f"доп оборот {format_money(summary.extra_revenue)}"
    )


def render_full_report(summary: ReportSummary, employee_label: str | None = None) -> str:
    """Полный финансовый отчет — только для администраторов."""
    parts: list[str] = [f"<b>{_header(summary.report_date, summary.city_name)}</b>"]
    parts.extend(_category_blocks(summary))

    rate = format_salary_rate(summary.salary_kind, summary.salary_value)
    parts.append(f"<b>ОБЩАЯ ВЫРУЧКА — {format_money(summary.total_revenue)}</b>")
    parts.append(
        f"МЕНЕДЖЕРУ ({_percent_label(MANAGER_SHARE)}) — "
        f"{format_money(summary.manager_amount)}"
    )
    parts.append(f"РАБОТНИКАМ ({rate}) — {format_money(summary.salary_amount)}")
    if summary.expense_amount or summary.expense_kind != EXPENSE_NONE:
        parts.append(
            f"РАСХОД ({format_expense_rate(summary.expense_kind, summary.expense_value)}) "
            f"— {format_money(summary.expense_amount)}"
        )

    if summary.plan > 0:
        over = summary.month_revenue - summary.plan
        progress = (
            f"перевыполнение {format_money(over)}"
            if over > 0
            else f"до плана {format_money(-over)}"
        )
        parts.append(
            f"ПЕРЕВЫПОЛНЕНИЕ ({_percent_label(BONUS_SHARE)}) — "
            f"{format_money(summary.bonus)}\n"
            f"Касса месяца — {format_money(summary.month_revenue)} "
            f"при плане {format_money(summary.plan)} ({progress})"
        )

    parts.append(f"ОБЩАЯ СЕБЕСТОИМОСТЬ — {format_money(summary.total_cost)}")
    parts.append(f"<b>ЧИСТАЯ — {format_money(summary.net_profit)}</b>")
    parts.append(f"CARLGAUSS — {format_money(summary.carlgauss)}")
    parts.append(f"ОСТАТОК — {format_money(summary.remainder)}")

    if employee_label:
        parts.append(f"<i>Отчет заполнил: {escape(employee_label)}</i>")

    return "\n\n".join(parts)


def period_title(kind: str, start: date, end: date, city_name: str | None = None) -> str:
    """'📅 Неделя 01.09–07.09 · Рига' или '🗓 Месяц 09.2025 · Рига'."""
    if kind == PERIOD_WEEK:
        text = f"📅 Неделя {dates.format_range(start, end)}"
    else:
        text = f"🗓 Месяц {dates.format_month(dates.month_key(start))}"
    if city_name:
        text += f" · {escape(city_name)}"
    return text


def render_period_report(summary: PeriodSummary) -> str:
    """Сводка за неделю или месяц по городу — только для администраторов."""
    title = period_title(summary.kind, summary.start, summary.end, summary.city_name)
    if not summary.days:
        return f"<b>{title}</b>\n\nЗа этот период отчетов нет."

    parts: list[str] = [f"<b>{title}</b>"]
    parts.extend(_category_blocks(summary))

    day_lines = [f"<b>ПО ДНЯМ ({summary.reports_count}):</b>", ""]
    for day in summary.days:
        day_lines.append(
            f"{dates.format_short(day.report_date)} — "
            f"{format_money(day.revenue)} / {format_quantity(day.quantity)} / "
            f"{day.customers_count} чел."
        )
    parts.append("\n".join(day_lines))

    parts.append(f"<b>ОБЩАЯ ВЫРУЧКА — {format_money(summary.total_revenue)}</b>")
    parts.append(
        f"МЕНЕДЖЕРУ ({_percent_label(MANAGER_SHARE)}) — "
        f"{format_money(summary.manager_amount)}"
    )
    rate = (
        f" ({format_salary_rate(*summary.salary_rate)})" if summary.salary_rate else ""
    )
    parts.append(f"РАБОТНИКАМ{rate} — {format_money(summary.salary_amount)}")
    if summary.expense_amount:
        expense = (
            f" ({format_expense_rate(*summary.expense_rate)})"
            if summary.expense_rate
            else ""
        )
        parts.append(f"РАСХОД{expense} — {format_money(summary.expense_amount)}")
    if summary.bonus:
        parts.append(
            f"ПЕРЕВЫПОЛНЕНИЕ ({_percent_label(BONUS_SHARE)}) — "
            f"{format_money(summary.bonus)}"
        )
    parts.append(f"ОБЩАЯ СЕБЕСТОИМОСТЬ — {format_money(summary.total_cost)}")
    parts.append(f"<b>ЧИСТАЯ — {format_money(summary.net_profit)}</b>")
    parts.append(f"CARLGAUSS — {format_money(summary.carlgauss)}")
    parts.append(f"ОСТАТОК — {format_money(summary.remainder)}")
    return "\n\n".join(parts)


def _employee_lines(summary: ReportSummary, with_revenue: bool = False) -> list[str]:
    """Строки по позициям для работника: группами, без экономики."""
    rows: list[str] = []
    current_group = None
    for line in summary.lines:
        if line.group_key != current_group:
            current_group = line.group_key
            rows.append(f"<b>{GROUP_TITLES.get(current_group, current_group)}</b>")
        text = f"{escape(line.name)} — {format_quantity(line.quantity)}"
        if with_revenue:
            text += f" / {format_money(line.revenue)}"
        if line.shows_customers:
            text += (
                f" / {line.customers_count} клиентов / UPD {format_upd(line.upd)}"
            )
        rows.append(text)
    return rows


def render_employee_result(summary: ReportSummary) -> str:
    """Безопасная версия для работника — без закупок, себестоимости и прибыли."""
    lines = [
        f"Отчет за {_header(summary.report_date, summary.city_name)} сохранен ✅",
        "",
    ]
    lines.extend(_employee_lines(summary))
    lines.extend(
        [
            "",
            f"Продано жидкостей: {summary.liquid_quantity}",
            f"UPD: {format_upd(summary.upd)}",
            f"Общая выручка: {format_money(summary.total_revenue)}",
            _outreach_line(summary),
        ]
    )
    return "\n".join(lines)


def render_employee_summary(summary: ReportSummary) -> str:
    """Безопасный просмотр сохраненного отчета работником."""
    header = _header(summary.report_date, summary.city_name, full_date=True)
    lines = [f"<b>Отчет за {header}</b>", ""]
    lines.extend(_employee_lines(summary, with_revenue=True))
    lines.extend(
        [
            "",
            f"Продано жидкостей: {summary.liquid_quantity}",
            f"Покупателей: {summary.customers_count}",
            f"UPD: {format_upd(summary.upd)}",
            f"Общая выручка: {format_money(summary.total_revenue)}",
            _outreach_line(summary),
        ]
    )
    return "\n".join(lines)


def render_preview(
    report_date: date,
    rows: Sequence[tuple[str, str, int, float, int | None]],
    customers_count: int,
    city_name: str | None = None,
    outreach: tuple[int, int, int, float] | None = None,
) -> str:
    """Предпросмотр перед сохранением (данные работника, без экономики).

    Строка: (группа, название, количество, выручка, клиенты или None).
    """
    header = _header(report_date, city_name, full_date=True)
    lines = [f"<b>Проверьте отчет за {header}</b>", ""]
    current_group = None
    for group_key, name, quantity, revenue, clients in rows:
        if group_key != current_group:
            current_group = group_key
            lines.append(f"<b>{GROUP_TITLES.get(group_key, group_key)}</b>")
        text = (
            f"{escape(name)} — {format_quantity(quantity)} / "
            f"{format_money(revenue)}"
        )
        if clients is not None:
            text += f" / {clients} клиентов"
        lines.append(text)
    lines.append("")
    lines.append(f"Покупателей — {customers_count}")
    if outreach is not None:
        touches, replies, purchases, extra_revenue = outreach
        if touches:
            lines.append(
                f"Рассылки — {touches} касаний / {replies} ответили / "
                f"{purchases} покупок / доп оборот {format_money(extra_revenue)}"
            )
        else:
            lines.append("Рассылки — не было")
    return "\n".join(lines)


def render_prices(categories: Sequence[Category]) -> str:
    """Текущие закупочные цены — только для администраторов."""
    if not categories:
        return "Категорий пока нет."
    lines = ["<b>Текущие закупочные цены</b>", ""]
    current_group = None
    for category in categories:
        if category.group_key != current_group:
            current_group = category.group_key
            lines.append(f"<b>{category.group_title}</b>")
        status = "" if category.active else " (выключена)"
        lines.append(
            f"{escape(category.name)}{status} — "
            f"{format_money(category.purchase_price)}"
        )
    return "\n".join(lines)


def render_plans(city: City, plans: Sequence[tuple[str, float]]) -> str:
    """Планы города по месяцам — от них считается бонус за перевыполнение."""
    lines = [f"🎯 <b>План {escape(city.name)}</b>", ""]
    for month, amount in plans:
        value = format_money(amount) if amount > 0 else "не задан"
        lines.append(f"{dates.format_month(month)} — {value}")
    lines.append("")
    lines.append(
        f"Работникам идет {_percent_label(BONUS_SHARE)} от кассы месяца, "
        "которая превысила план. Без плана бонус не начисляется."
    )
    return "\n".join(lines)


def render_cities(cities: Sequence[City]) -> str:
    if not cities:
        return (
            "Городов пока нет.\n\n"
            "Пока не добавлен ни один город, работник не сможет отправить отчет."
        )
    lines = ["<b>Города</b>", ""]
    for city in cities:
        status = "включен" if city.active else "выключен"
        rate = format_salary_rate(city.salary_kind, city.salary_value)
        lines.append(
            f"🏙 {escape(city.name)} — {status}, работникам {rate}"
        )
    lines.append("")
    lines.append("Нажмите на город, чтобы открыть его настройки.")
    return "\n".join(lines)


def render_city_card(city: City, plan: float = 0.0, plan_month: str = "") -> str:
    rate = format_salary_rate(city.salary_kind, city.salary_value)
    plan_text = format_money(plan) if plan > 0 else "не задан"
    month_text = f" ({dates.format_month(plan_month)})" if plan_month else ""
    return (
        f"🏙 <b>{escape(city.name)}</b>\n\n"
        f"Статус: {'включен' if city.active else 'выключен'}\n"
        f"Минус работникам: {rate}\n"
        f"Фикс-расход: {format_expense_rate(city.expense_kind, city.expense_value)}\n"
        f"План{month_text}: {plan_text}\n"
        f"Менеджеру: {_percent_label(MANAGER_SHARE)} от оборота (во всех городах)"
    )


def render_pots(
    balances: Sequence[PotBalance], payouts: Sequence[Payout] | None = None
) -> str:
    """Три копилки: сколько набежало, сколько выплатили, сколько осталось."""
    lines = ["<b>Касса</b>", ""]
    for item in balances:
        lines.append(
            f"<b>{escape(item.title)}</b> — {format_money(item.balance)}\n"
            f"накоплено {format_money(item.accrued)}, "
            f"выплачено {format_money(item.paid)}"
        )
    if payouts:
        lines.append("")
        lines.append("<b>Последние выплаты</b>")
        for payout in payouts:
            stamp = payout.created_at.replace("T", " ")
            lines.append(
                f"{stamp} — {escape(payout.title)} {format_money(payout.amount)}"
            )
    return "\n\n".join(lines)


def render_reports_list(reports: Sequence[ReportBrief], title: str) -> str:
    if not reports:
        return "Сохраненных отчетов пока нет."
    lines = [f"<b>{escape(title)}</b>", ""]
    for report in reports:
        lines.append(
            f"{_header(report.date, report.city_name, full_date=True)} — "
            f"{format_quantity(report.total_quantity)} / "
            f"{format_money(report.total_revenue)}"
        )
    lines.append("")
    lines.append("Выберите отчет кнопкой ниже, чтобы открыть его.")
    return "\n".join(lines)
