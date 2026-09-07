"""Сборка текстов: полный отчет для админа, безопасный — для работника."""

from __future__ import annotations

from datetime import date
from html import escape
from typing import Sequence

from config import config
from database import Category, ReportBrief
from services.calculations import ReportSummary
from utils import dates
from utils.formatting import format_money, format_quantity, format_upd


def render_full_report(summary: ReportSummary, employee_label: str | None = None) -> str:
    """Полный финансовый отчет — только для администраторов."""
    parts: list[str] = [f"<b>{dates.format_short(summary.report_date)}</b>"]

    for line in summary.lines:
        parts.append(
            f"<b>{escape(line.name)}:</b>\n\n"
            f"Количество — {format_quantity(line.quantity)}\n"
            f"Выручка — {format_money(line.revenue)}\n"
            f"Средний чек — {format_money(line.average_check)}\n"
            f"Себестоимость — {format_money(line.cost)}\n"
            f"Чистая прибыль — {format_money(line.net_profit)}"
        )

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

    parts.append(f"<b>ОБЩАЯ ВЫРУЧКА — {format_money(summary.total_revenue)}</b>")
    parts.append(f"{config.tax_label} — {format_money(summary.tax_amount)}")
    parts.append(f"ОБЩАЯ СЕБЕСТОИМОСТЬ — {format_money(summary.total_cost)}")
    parts.append(f"<b>ЧИСТАЯ ПРИБЫЛЬ — {format_money(summary.net_profit)}</b>")

    if employee_label:
        parts.append(f"<i>Отчет заполнил: {escape(employee_label)}</i>")

    return "\n\n".join(parts)


def render_employee_result(summary: ReportSummary) -> str:
    """Безопасная версия для работника — без закупок, себестоимости и прибыли."""
    return (
        f"Отчет за {dates.format_short(summary.report_date)} сохранен ✅\n\n"
        f"Продано жидкостей: {summary.liquid_quantity}\n"
        f"UPD: {format_upd(summary.upd)}\n"
        f"Общая выручка: {format_money(summary.total_revenue)}"
    )


def render_employee_summary(summary: ReportSummary) -> str:
    """Безопасный просмотр сохраненного отчета работником."""
    lines = [f"<b>Отчет за {dates.format_full(summary.report_date)}</b>", ""]
    for line in summary.lines:
        lines.append(
            f"{escape(line.name)} — {format_quantity(line.quantity)} / "
            f"{format_money(line.revenue)}"
        )
    lines.extend(
        [
            "",
            f"Продано жидкостей: {summary.liquid_quantity}",
            f"Покупателей: {summary.customers_count}",
            f"UPD: {format_upd(summary.upd)}",
            f"Общая выручка: {format_money(summary.total_revenue)}",
        ]
    )
    return "\n".join(lines)


def render_preview(
    report_date: date,
    rows: Sequence[tuple[str, int, float]],
    customers_count: int,
) -> str:
    """Предпросмотр перед сохранением (данные работника, без экономики)."""
    lines = [f"<b>Проверьте отчет за {dates.format_full(report_date)}</b>", ""]
    for name, quantity, revenue in rows:
        lines.append(
            f"{escape(name)} — {format_quantity(quantity)} / {format_money(revenue)}"
        )
    lines.append("")
    lines.append(f"Покупателей — {customers_count}")
    return "\n".join(lines)


def render_prices(categories: Sequence[Category]) -> str:
    """Текущие закупочные цены — только для администраторов."""
    if not categories:
        return "Категорий пока нет."
    lines = ["<b>Текущие закупочные цены</b>", ""]
    for category in categories:
        mark = "💧" if category.is_liquid else "🔧"
        status = "" if category.active else " (выключена)"
        lines.append(
            f"{mark} {escape(category.name)}{status} — "
            f"{format_money(category.purchase_price)}"
        )
    return "\n".join(lines)


def render_reports_list(reports: Sequence[ReportBrief], title: str) -> str:
    if not reports:
        return "Сохраненных отчетов пока нет."
    lines = [f"<b>{escape(title)}</b>", ""]
    for report in reports:
        lines.append(
            f"{dates.format_full(report.date)} — "
            f"{format_quantity(report.total_quantity)} / "
            f"{format_money(report.total_revenue)}"
        )
    lines.append("")
    lines.append("Выберите отчет кнопкой ниже, чтобы открыть его.")
    return "\n".join(lines)
