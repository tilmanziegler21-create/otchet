"""Связка расчетов с базой: бонус за перевыполнение и касса месяца."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import database as db
from services.calculations import (
    PERIOD_WEEK,
    PeriodSummary,
    ReportSummary,
    build_period_summary,
    calculate_bonus,
    summary_from_report,
)
from utils import dates


@dataclass(frozen=True)
class BonusContext:
    bonus: float
    plan: float
    month_revenue: float


async def resolve_bonus(
    city_id: int | None,
    report_date: date,
    day_revenue: float,
    exclude_report_id: int | None = None,
) -> BonusContext:
    """Бонус дня = 25% от прироста кассы месяца сверх плана города."""
    if city_id is None:
        return BonusContext(bonus=0.0, plan=0.0, month_revenue=day_revenue)

    month = dates.month_key(report_date)
    plan = await db.get_monthly_plan(city_id, month)
    revenue_before = await db.get_month_revenue(
        city_id, month, exclude_report_id=exclude_report_id
    )
    return BonusContext(
        bonus=calculate_bonus(revenue_before, day_revenue, plan),
        plan=plan,
        month_revenue=revenue_before + day_revenue,
    )


async def summary_for_report(report: db.Report) -> ReportSummary:
    """Расчеты сохраненного отчета вместе с кассой его месяца."""
    month_revenue = 0.0
    if report.city_id is not None:
        month_revenue = await db.get_month_revenue(
            report.city_id, dates.month_key(report.date)
        )
    return summary_from_report(report, month_revenue=month_revenue)


def period_bounds(kind: str, offset: int) -> tuple[date, date]:
    """Границы периода: offset 0 — текущий, -1 — предыдущий и так далее."""
    today = dates.today()
    if kind == PERIOD_WEEK:
        return dates.week_bounds(dates.shift_week(today, offset))
    return dates.month_bounds(dates.shift_month(today, offset))


async def summary_for_period(
    kind: str, offset: int, city_id: int, city_name: str | None = None
) -> PeriodSummary:
    """Недельная или месячная сводка одного города."""
    start, end = period_bounds(kind, offset)
    reports = await db.get_reports_between(
        dates.to_db(start), dates.to_db(end), city_id=city_id
    )
    return build_period_summary(
        reports, kind=kind, start=start, end=end, city_name=city_name
    )
