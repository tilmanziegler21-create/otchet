"""Рассылка полного отчета администраторам."""

from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from config import config
from keyboards.admin import pots_menu, report_card_menu
from services.calculations import ReportSummary
from services.pots import PotBalance
from services.report_builder import render_full_report
from utils.formatting import format_money

logger = logging.getLogger(__name__)


async def send_report_to_admins(
    bot: Bot,
    summary: ReportSummary,
    employee_label: str | None = None,
    skip_ids: tuple[int, ...] = (),
) -> None:
    if not config.admin_ids:
        logger.warning("ADMIN_IDS пуст — полный отчет отправить некому.")
        return

    text = "🧾 <b>Новый отчет</b>\n\n" + render_full_report(summary, employee_label)
    markup = report_card_menu(summary.report_id) if summary.report_id else None
    for admin_id in config.admin_ids:
        if admin_id in skip_ids:
            continue
        try:
            await bot.send_message(admin_id, text, reply_markup=markup)
        except TelegramAPIError as error:
            logger.warning("Не удалось отправить отчет админу %s: %s", admin_id, error)


async def send_payout_to_admins(
    bot: Bot,
    item: PotBalance,
    amount: float,
    actor_label: str,
    skip_ids: tuple[int, ...] = (),
) -> None:
    """Сообщает всем админам, что из копилки сняли выплату."""
    text = (
        f"💸 <b>Выплата</b>\n\n"
        f"{item.title} — {format_money(amount)}\n"
        f"Остаток копилки: {format_money(item.balance)}\n"
        f"Выплатил: {actor_label}"
    )
    for admin_id in config.admin_ids:
        if admin_id in skip_ids:
            continue
        try:
            await bot.send_message(admin_id, text, reply_markup=pots_menu())
        except TelegramAPIError as error:
            logger.warning("Не удалось отправить выплату админу %s: %s", admin_id, error)
