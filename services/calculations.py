"""Все расчеты отчета.

Экономика собрана в функциях этого модуля — чтобы менять ее в одном месте.

Текущая логика:
    менеджеру       = 5% от дневного оборота (в каждом городе)
    работникам      = процент от оборота, фикс за день
                      или фикс за месяц / число дней месяца
    перевыполнение  = 25% от кассы месяца, превысившей план города
    чистая          = оборот - менеджеру - работникам - перевыполнение
                      - фикс-расход города - закуп
    CARLGAUSS       = 1/4 чистой
    ОСТАТОК         = чистая - CARLGAUSS
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Sequence

from database import (
    EXPENSE_FIXED,
    EXPENSE_MONTHLY,
    EXPENSE_NONE,
    GROUP_LIQUID,
    GROUPS_WITH_CUSTOMERS,
    SALARY_FIXED,
    SALARY_MONTHLY,
    SALARY_PERCENT,
    Report,
)
from utils import dates
from utils.formatting import round_money

# Доля Carlgauss в чистой прибыли.
CARLGAUSS_SHARE = 0.25
# Менеджеру от дневного оборота — одинаково во всех городах.
MANAGER_SHARE = 0.05
# Работникам от кассы, превысившей месячный план.
BONUS_SHARE = 0.25

# Периоды сводных отчетов.
PERIOD_WEEK = "week"
PERIOD_MONTH = "month"


def calculate_manager(total_revenue: float) -> float:
    """5% менеджеру от общего дневного оборота."""
    return float(total_revenue) * MANAGER_SHARE


def calculate_salary(
    total_revenue: float,
    salary_kind: str,
    salary_value: float,
    report_date: date | None = None,
) -> float:
    """«Минус работникам»: процент, фикс за день или фикс за месяц."""
    if salary_kind == SALARY_FIXED:
        return float(salary_value)
    if salary_kind == SALARY_MONTHLY:
        days = dates.days_in_month(report_date) if report_date else 30
        return float(salary_value) / days
    return float(total_revenue) * float(salary_value) / 100


def calculate_bonus(
    month_revenue_before: float, day_revenue: float, plan: float
) -> float:
    """25% от той части кассы месяца, что превысила план.

    Считается приростом: бонус дня = 25% от превышения на конец дня минус
    25% от превышения на начало дня. Без плана (0) бонуса нет.
    """
    if plan <= 0:
        return 0.0
    before = max(0.0, float(month_revenue_before) - float(plan))
    after = max(0.0, float(month_revenue_before) + float(day_revenue) - float(plan))
    return (after - before) * BONUS_SHARE


def calculate_expense(
    expense_kind: str,
    expense_value: float,
    report_date: date | None = None,
) -> float:
    """Доп. расход города: фикс за день, фикс за месяц / дни, либо ноль."""
    if expense_kind == EXPENSE_FIXED:
        return float(expense_value)
    if expense_kind == EXPENSE_MONTHLY:
        days = dates.days_in_month(report_date) if report_date else 30
        return float(expense_value) / days
    return 0.0


def calculate_net_profit(
    revenue: float,
    cost: float,
    salary: float,
    manager: float,
    bonus: float = 0.0,
    expense: float = 0.0,
) -> float:
    """Единственное место с формулой чистой прибыли."""
    return (
        float(revenue)
        - float(manager)
        - float(salary)
        - float(bonus)
        - float(expense)
        - float(cost)
    )


def calculate_carlgauss(net_profit: float) -> float:
    return round_money(float(net_profit) * CARLGAUSS_SHARE)


def calculate_remainder(net_profit: float) -> float:
    """Остаток для лиц — все, что не ушло Carlgauss (до цента)."""
    return round_money(round_money(net_profit) - calculate_carlgauss(net_profit))


def calculate_average_check(revenue: float, quantity: int) -> float:
    if not quantity:
        return 0.0
    return float(revenue) / int(quantity)


def calculate_upd(quantity: int, customers_count: int) -> float:
    """UPD = проданные штуки / покупатели (по жидкостям или по бренду)."""
    if not customers_count:
        return 0.0
    return round(int(quantity) / int(customers_count), 2)


def calculate_rate(part: int, whole: int) -> float:
    """Конверсия в процентах: ответившие от касаний, покупки от ответов."""
    if not whole:
        return 0.0
    return int(part) / int(whole) * 100


@dataclass(frozen=True)
class CategoryLine:
    category_id: int
    name: str
    is_liquid: bool
    quantity: int
    revenue: float
    purchase_price: float
    customers_count: int = 0
    group_key: str = GROUP_LIQUID

    @property
    def cost(self) -> float:
        """Себестоимость = количество * закупочная цена."""
        return self.quantity * self.purchase_price

    @property
    def average_check(self) -> float:
        return calculate_average_check(self.revenue, self.quantity)

    @property
    def upd(self) -> float:
        """UPD бренда — его штуки на одного клиента этого бренда."""
        return calculate_upd(self.quantity, self.customers_count)

    @property
    def shows_customers(self) -> bool:
        """Клиентов и UPD ведем только по жидкостям и электронкам."""
        return self.group_key in GROUPS_WITH_CUSTOMERS


class SummaryTotals:
    """Итоги, одинаковые для отчета за день и за период.

    Наследник обязан дать `lines`, `customers_count`, `manager_amount`,
    `salary_amount`, `bonus` и цифры рассылок — остальное считается отсюда.
    """

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
    def deductions(self) -> float:
        """Все, что уходит людям и на фикс-расход города."""
        return (
            self.manager_amount
            + self.salary_amount
            + self.bonus
            + self.expense_amount
        )

    @property
    def net_profit(self) -> float:
        """Главная цифра — строго по общей формуле, а не суммой категорий."""
        return calculate_net_profit(
            self.total_revenue,
            self.total_cost,
            self.salary_amount,
            self.manager_amount,
            self.bonus,
            self.expense_amount,
        )

    @property
    def carlgauss(self) -> float:
        return calculate_carlgauss(self.net_profit)

    @property
    def remainder(self) -> float:
        return calculate_remainder(self.net_profit)

    # ------------------------------------------------------- по категориям
    def category_deductions(self, line: CategoryLine) -> float:
        """Доля выплат людям, отнесенная на категорию пропорционально выручке."""
        total = self.total_revenue
        if not total:
            return 0.0
        return self.deductions * line.revenue / total

    def category_profit(self, line: CategoryLine) -> float:
        """Прибыль категории пропорционально ее выручке и себестоимости."""
        return line.revenue - self.category_deductions(line) - line.cost

    # ------------------------------------------------------------- рассылки
    @property
    def reply_rate(self) -> float:
        """Сколько процентов касаний ответили."""
        return calculate_rate(self.replies, self.touches)

    @property
    def purchase_rate(self) -> float:
        """Сколько процентов ответивших перешли к покупке."""
        return calculate_rate(self.purchases, self.replies)

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


@dataclass(frozen=True)
class ReportSummary(SummaryTotals):
    report_date: date
    customers_count: int
    lines: tuple[CategoryLine, ...]
    city_name: str | None = None
    salary_kind: str = SALARY_PERCENT
    salary_value: float = 0.0
    bonus: float = 0.0
    plan: float = 0.0
    month_revenue: float = 0.0
    touches: int = 0
    replies: int = 0
    purchases: int = 0
    extra_revenue: float = 0.0
    expense_kind: str = EXPENSE_NONE
    expense_value: float = 0.0
    report_id: int | None = None
    employee_telegram_id: int | None = None

    @property
    def manager_amount(self) -> float:
        return calculate_manager(self.total_revenue)

    @property
    def salary_amount(self) -> float:
        return calculate_salary(
            self.total_revenue, self.salary_kind, self.salary_value, self.report_date
        )

    @property
    def expense_amount(self) -> float:
        return calculate_expense(
            self.expense_kind, self.expense_value, self.report_date
        )


def build_summary(
    report_date: date,
    customers_count: int,
    lines: Sequence[CategoryLine],
    city_name: str | None = None,
    salary_kind: str = SALARY_PERCENT,
    salary_value: float = 0.0,
    bonus: float = 0.0,
    plan: float = 0.0,
    month_revenue: float = 0.0,
    touches: int = 0,
    replies: int = 0,
    purchases: int = 0,
    extra_revenue: float = 0.0,
    expense_kind: str = EXPENSE_NONE,
    expense_value: float = 0.0,
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
        bonus=bonus,
        plan=plan,
        month_revenue=month_revenue,
        touches=touches,
        replies=replies,
        purchases=purchases,
        extra_revenue=extra_revenue,
        expense_kind=expense_kind,
        expense_value=expense_value,
        report_id=report_id,
        employee_telegram_id=employee_telegram_id,
    )


@dataclass(frozen=True)
class PeriodLine:
    """Категория, сложенная за несколько дней: закуп берется суммой снимков."""

    category_id: int
    name: str
    is_liquid: bool
    quantity: int
    revenue: float
    cost: float
    customers_count: int = 0
    group_key: str = GROUP_LIQUID

    @property
    def average_check(self) -> float:
        return calculate_average_check(self.revenue, self.quantity)

    @property
    def upd(self) -> float:
        """UPD бренда за период — штуки / клиенты бренда за все дни."""
        return calculate_upd(self.quantity, self.customers_count)

    @property
    def shows_customers(self) -> bool:
        return self.group_key in GROUPS_WITH_CUSTOMERS


@dataclass(frozen=True)
class DayLine:
    report_date: date
    quantity: int
    revenue: float
    customers_count: int


@dataclass(frozen=True)
class PeriodSummary(SummaryTotals):
    """Сводка за неделю или месяц по одному городу.

    Выплаты не пересчитываются заново, а складываются из снимков дневных
    отчетов — поэтому цифры периода сходятся с тем, что уже видели по дням.
    """

    kind: str
    start: date
    end: date
    lines: tuple[PeriodLine, ...]
    days: tuple[DayLine, ...]
    customers_count: int
    salary_amount: float
    bonus: float
    expense_amount: float = 0.0
    touches: int = 0
    replies: int = 0
    purchases: int = 0
    extra_revenue: float = 0.0
    city_name: str | None = None
    salary_rate: tuple[str, float] | None = None
    expense_rate: tuple[str, float] | None = None

    @property
    def manager_amount(self) -> float:
        return calculate_manager(self.total_revenue)

    @property
    def reports_count(self) -> int:
        return len(self.days)


def build_period_summary(
    reports: Sequence[Report],
    kind: str,
    start: date,
    end: date,
    city_name: str | None = None,
) -> PeriodSummary:
    """Складывает дневные отчеты города в сводку за период."""
    categories: dict[int, dict] = {}
    days: dict[str, dict] = {}
    salary_amount = 0.0
    bonus = 0.0
    expense_amount = 0.0
    rates: set[tuple[str, float]] = set()
    expense_rates: set[tuple[str, float]] = set()

    for report in reports:
        report_revenue = sum(item.revenue for item in report.items)
        report_quantity = sum(item.quantity for item in report.items)
        report_date = dates.from_db(report.date)
        salary_amount += calculate_salary(
            report_revenue,
            report.salary_kind,
            report.salary_value,
            report_date,
        )
        expense_amount += calculate_expense(
            report.expense_kind, report.expense_value, report_date
        )
        bonus += report.bonus
        rates.add((report.salary_kind, report.salary_value))
        if report.expense_kind != EXPENSE_NONE:
            expense_rates.add((report.expense_kind, report.expense_value))

        day = days.setdefault(
            report.date, {"quantity": 0, "revenue": 0.0, "customers": 0}
        )
        day["quantity"] += report_quantity
        day["revenue"] += report_revenue
        day["customers"] += report.customers_count

        for item in report.items:
            line = categories.setdefault(
                item.category_id,
                {
                    "name": item.name,
                    "is_liquid": item.is_liquid,
                    "group_key": item.group_key,
                    "quantity": 0,
                    "revenue": 0.0,
                    "cost": 0.0,
                    "customers": 0,
                },
            )
            line["quantity"] += item.quantity
            line["revenue"] += item.revenue
            line["cost"] += item.quantity * item.purchase_price_snapshot
            line["customers"] += item.customers_count

    return PeriodSummary(
        kind=kind,
        start=start,
        end=end,
        lines=tuple(
            PeriodLine(
                category_id=category_id,
                name=line["name"],
                is_liquid=line["is_liquid"],
                quantity=line["quantity"],
                revenue=line["revenue"],
                cost=line["cost"],
                customers_count=line["customers"],
                group_key=line["group_key"],
            )
            for category_id, line in categories.items()
        ),
        days=tuple(
            DayLine(
                report_date=dates.from_db(report_date),
                quantity=day["quantity"],
                revenue=day["revenue"],
                customers_count=day["customers"],
            )
            for report_date, day in sorted(days.items())
        ),
        customers_count=sum(day["customers"] for day in days.values()),
        salary_amount=salary_amount,
        bonus=bonus,
        expense_amount=expense_amount,
        touches=sum(report.touches for report in reports),
        replies=sum(report.replies for report in reports),
        purchases=sum(report.purchases for report in reports),
        extra_revenue=sum(report.extra_revenue for report in reports),
        city_name=city_name,
        salary_rate=rates.pop() if len(rates) == 1 else None,
        expense_rate=expense_rates.pop() if len(expense_rates) == 1 else None,
    )


def summary_from_report(report: Report, month_revenue: float = 0.0) -> ReportSummary:
    """Собирает расчеты из сохраненного отчета (по сохраненным снимкам)."""
    lines = [
        CategoryLine(
            category_id=item.category_id,
            name=item.name,
            is_liquid=item.is_liquid,
            quantity=item.quantity,
            revenue=item.revenue,
            purchase_price=item.purchase_price_snapshot,
            customers_count=item.customers_count,
            group_key=item.group_key,
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
        bonus=report.bonus,
        plan=report.plan,
        month_revenue=month_revenue,
        touches=report.touches,
        replies=report.replies,
        purchases=report.purchases,
        extra_revenue=report.extra_revenue,
        expense_kind=report.expense_kind,
        expense_value=report.expense_value,
        report_id=report.id,
        employee_telegram_id=report.employee_telegram_id,
    )
