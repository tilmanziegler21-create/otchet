"""Все расчеты отчета.

Формула чистой прибыли вынесена в отдельные функции `calculate_tax`
и `calculate_net_profit` — чтобы менять экономику в одном месте.

Текущая логика:
    30%           = выручка * TAX_RATE
    чистая прибыль = выручка - 30% - себестоимость
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from config import config
from database import Report
from utils import dates


def calculate_tax(revenue: float, tax_rate: float | None = None) -> float:
    """30% от выручки (ставка настраивается через TAX_RATE в .env)."""
    rate = config.tax_rate if tax_rate is None else tax_rate
    return float(revenue) * rate


def calculate_net_profit(
    revenue: float, cost: float, tax_rate: float | None = None
) -> float:
    """Единственное место с формулой чистой прибыли."""
    return float(revenue) - calculate_tax(revenue, tax_rate) - float(cost)


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

    @property
    def net_profit(self) -> float:
        """Прибыль категории пропорционально ее выручке и себестоимости."""
        return calculate_net_profit(self.revenue, self.cost)


@dataclass(frozen=True)
class ReportSummary:
    report_date: date
    customers_count: int
    lines: tuple[CategoryLine, ...]
    city_name: str | None = None
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
    def tax_amount(self) -> float:
        return calculate_tax(self.total_revenue)

    @property
    def net_profit(self) -> float:
        """Главная цифра — строго по общей формуле, а не суммой категорий."""
        return calculate_net_profit(self.total_revenue, self.total_cost)

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
    report_id: int | None = None,
    employee_telegram_id: int | None = None,
) -> ReportSummary:
    return ReportSummary(
        report_date=report_date,
        customers_count=customers_count,
        lines=tuple(lines),
        city_name=city_name,
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
        report_id=report.id,
        employee_telegram_id=report.employee_telegram_id,
    )
