"""Накопительные копилки: менеджер, CARLGAUSS, остаток.

Баланс = сумма из сохраненных отчетов минус выплаты. Удаленный отчет
сам вычитается из накопления — отдельный пересчет не нужен.
"""

from __future__ import annotations

from dataclasses import dataclass

import database as db
from services.calculations import summary_from_report
from utils.formatting import round_money


@dataclass(frozen=True)
class PotBalance:
    pot: str
    title: str
    accrued: float
    paid: float

    @property
    def balance(self) -> float:
        return round_money(self.accrued - self.paid)


async def pot_balances() -> tuple[PotBalance, ...]:
    accrued = {pot: 0.0 for pot in db.POTS}
    for report in await db.get_all_reports():
        summary = summary_from_report(report)
        accrued[db.POT_MANAGER] += summary.manager_amount
        accrued[db.POT_CARLGAUSS] += summary.carlgauss
        accrued[db.POT_REMAINDER] += summary.remainder
    paid = await db.sum_payouts()
    return tuple(
        PotBalance(
            pot=pot,
            title=db.POT_TITLES[pot],
            accrued=round_money(accrued[pot]),
            paid=round_money(paid[pot]),
        )
        for pot in db.POTS
    )


def balance_for(balances: tuple[PotBalance, ...], pot: str) -> PotBalance | None:
    return next((item for item in balances if item.pot == pot), None)
