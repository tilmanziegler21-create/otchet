"""Команды /report_today и /reports.

Админ видит полный финансовый отчет, работник — только безопасную версию.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import database as db
from config import config
from keyboards.admin import reports_menu
from keyboards.employee import (
    BTN_MY_REPORTS,
    BTN_TODAY_REPORT,
    CB_EMPLOYEE_REPORT,
    employee_reports_menu,
)
from services.calculations import summary_from_report
from services.report_builder import (
    render_employee_summary,
    render_full_report,
    render_reports_list,
)
from utils import dates

router = Router(name="reports")

REPORTS_LIMIT = 10


async def _send_today(message: Message) -> None:
    if message.from_user is None:
        return
    is_admin = config.is_admin(message.from_user.id)
    report_date = dates.to_db(dates.today())
    reports = await db.get_reports_by_date(
        report_date,
        employee_telegram_id=None if is_admin else message.from_user.id,
    )
    if not reports:
        await message.answer(
            f"Отчет за {dates.format_full(report_date)} еще не заполнен."
        )
        return
    # По одному сообщению на город.
    for report in reports:
        summary = summary_from_report(report)
        if is_admin:
            await message.answer(
                render_full_report(summary, f"ID {report.employee_telegram_id}")
            )
        else:
            await message.answer(render_employee_summary(summary))


async def _send_reports_list(message: Message) -> None:
    if message.from_user is None:
        return
    is_admin = config.is_admin(message.from_user.id)
    if is_admin:
        reports = await db.list_reports(limit=REPORTS_LIMIT)
        if not reports:
            await message.answer("Сохраненных отчетов пока нет.")
            return
        await message.answer(
            render_reports_list(reports, "Последние отчеты"),
            reply_markup=reports_menu(reports),
        )
        return

    reports = await db.list_reports(
        limit=REPORTS_LIMIT, employee_telegram_id=message.from_user.id
    )
    if not reports:
        await message.answer("Вы еще не сохранили ни одного отчета.")
        return
    await message.answer(
        render_reports_list(reports, "Ваши последние отчеты"),
        reply_markup=employee_reports_menu(reports),
    )


@router.message(Command("report_today"))
async def cmd_report_today(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _send_today(message)


@router.message(F.text == BTN_TODAY_REPORT)
async def btn_report_today(message: Message) -> None:
    await _send_today(message)


@router.message(Command("reports"))
async def cmd_reports(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _send_reports_list(message)


@router.message(F.text == BTN_MY_REPORTS)
async def btn_my_reports(message: Message) -> None:
    await _send_reports_list(message)


@router.callback_query(F.data.startswith(CB_EMPLOYEE_REPORT))
async def show_employee_report(callback: CallbackQuery) -> None:
    raw_id = (callback.data or "")[len(CB_EMPLOYEE_REPORT) :]
    if not raw_id.isdigit() or callback.from_user is None:
        await callback.answer("Некорректный отчет", show_alert=True)
        return
    report = await db.get_report(int(raw_id))
    if report is None:
        await callback.answer("Отчет не найден", show_alert=True)
        return
    is_admin = config.is_admin(callback.from_user.id)
    if not is_admin and report.employee_telegram_id != callback.from_user.id:
        await callback.answer("Этот отчет вам недоступен", show_alert=True)
        return
    summary = summary_from_report(report)
    if callback.message is not None:
        await callback.message.answer(render_employee_summary(summary))
    await callback.answer()
