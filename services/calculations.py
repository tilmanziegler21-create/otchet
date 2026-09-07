"""Все расчеты отчета.

Экономика собрана в функциях `calculate_salary`, `calculate_net_profit`,
`calculate_carlgauss` и `calculate_remainder` — чтобы менять ее в одном месте.

Текущая логика:
    работникам = процент от общей выручки города или фикс за день
    чистая     = общая выручка - работникам - общая себестоимость
    CARLGAUSS  = 1/4 чистой
    ОСТАТОК    = чистая - CARLGAUSS
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from database import SALARY_FIXED, SALARY_PERCENT, Report
from utils import dates
from utils.formatting import round_money

# Доля Carlgauss в чистой прибыли.
CARLGAUSS_SHARE = 0.25


def calculate_salary(
    total_revenue: float, salary_kind: str, salary_value: float
) -> float:
    """«Минус работникам»: свой процент или фикс в каждом городе."""
    if salary_kind == SALARY_FIXED:
        return float(salary_value)
    return float(total_revenue) * float(salary_value) / 100


def calculate_net_profit(revenue: float, cost: float, salary: float) -> float:
    """Единственное место с формулой чистой прибыли."""
    return float(revenue) - float(salary) - float(cost)


def calculate_carlgauss(net_profit: float) -> float:
    return round_money(float(net_profit) * CARLGAUSS_SHARE)


def calculate_remainder(net_profit: float) -> float:
    """Остаток для лиц — все, что не ушло Carlgauss (до цента)."""
    return round_money(round_money(net_profit) - calculate_carlgauss(net_profit))


def calculate_average_check(revenue: float, quantity: int) -> float:
    if not quantity:
        return 0.0
    return float(revenue) / int(quantity)


def calculate_upd(liquid_quantity: int, customers_count: int) -> float:
    """UPD = проданные жидкости / покупатели."""
    if not customers_count:
        return 0.0
    return round(int(liquid_quantity) / int(customers_count), 2)


@dataclass(frozen=True)
class CategoryLine:
    category_id: int
    name: str
    is_liquid: bool
    quantity: int
    revenue: float
    purchase_price: float

    @property
    def cost(self) -> float:
        """Себестоимость = количество * закупочная цена."""
        return self.quantity * self.purchase_price

    @property
    def average_check(self) -> float:
        return calculate_average_check(self.revenue, self.quantity)


@dataclass(frozen=True)
class ReportSummary:
    report_date: date
    customers_count: int
    lines: tuple[CategoryLine, ...]
    city_name: str | None = None
    salary_kind: str = SALARY_PERCENT
    salary_value: float = 0.0
    report_id: int | None = None
    employee_telegram_id: int | None = None

    # ---------------------------------------------------------- общие итоги
    @property
    def total_quantity(self) -> int:
        return sum(line.quantity for line in self.lines)

    @property
    def total_revenue(self) -> float:
        return sum(line.revenue for line in self.lines)

    @property
    def total_cost(self) -> float:
        return sum(line.cost for line in self.lines)

    @property
    def salary_amount(self) -> float:
        return calculate_salary(
            self.total_revenue, self.salary_kind, self.salary_value
        )

    @property
    def net_profit(self) -> float:
        """Главная цифра — строго по общей формуле, а не суммой категорий."""
        return calculate_net_profit(
            self.total_revenue, self.total_cost, self.salary_amount
        )

    @property
    def carlgauss(self) -> float:
        return calculate_carlgauss(self.net_profit)

    @property
    def remainder(self) -> float:
        return calculate_remainder(self.net_profit)

    # ------------------------------------------------------- по категориям
    def category_salary(self, line: CategoryLine) -> float:
        """Доля «работникам», отнесенная на категорию пропорционально выручке."""
        total = self.total_revenue
        if not total:
            return 0.0
        return self.salary_amount * line.revenue / total

    def category_profit(self, line: CategoryLine) -> float:
        """Прибыль категории пропорционально ее выручке и себестоимости."""
        return calculate_net_profit(
            line.revenue, line.cost, self.category_salary(line)
        )

    # ------------------------------------------------------------- жидкости
    @property
    def liquid_lines(self) -> tuple[CategoryLine, ...]:
        return tuple(line for line in self.lines if line.is_liquid)

    @property
    def liquid_quantity(self) -> int:
        return sum(line.quantity for line in self.liquid_lines)

    @property
    def liquid_revenue(self) -> float:
        return sum(line.revenue for line in self.liquid_lines)

    @property
    def liquid_average_check(self) -> float:
        return calculate_average_check(self.liquid_revenue, self.liquid_quantity)

    @property
    def upd(self) -> float:
        return calculate_upd(self.liquid_quantity, self.customers_count)


def build_summary(
    report_date: date,
    customers_count: int,
    lines: Sequence[CategoryLine],
    city_name: str | None = None,
    salary_kind: str = SALARY_PERCENT,
    salary_value: float = 0.0,
    report_id: int | None = None,
    employee_telegram_id: int | None = None,
) -> ReportSummary:
    return ReportSummary(
        report_date=report_date,
        customers_count=customers_count,
        lines=tuple(lines),
        city_name=city_name,
        salary_kind=salary_kind,
        salary_value=salary_value,
        report_id=report_id,
        employee_telegram_id=employee_telegram_id,
    )


def summary_from_report(report: Report) -> ReportSummary:
    """Собирает расчеты из сохраненного отчета (по снимку закупочных цен)."""
    lines = [
        CategoryLine(
            category_id=item.category_id,
            name=item.name,
            is_liquid=item.is_liquid,
            quantity=item.quantity,
            revenue=item.revenue,
            purchase_price=item.purchase_price_snapshot,
        )
        for item in report.items
    ]
    return build_summary(
        report_date=dates.from_db(report.date),
        customers_count=report.customers_count,
        lines=lines,
        city_name=report.city_name,
        salary_kind=report.salary_kind,
        salary_value=report.salary_value,
        report_id=report.id,
        employee_telegram_id=report.employee_telegram_id,
    )
