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
from keyboards.admin import (
    CB_REPORTS_PAGE,
    REPORTS_PAGE_SIZE,
    report_card_menu,
    reports_menu,
)
from keyboards.employee import (
    BTN_MY_REPORTS,
    BTN_TODAY_REPORT,
    CB_EMP_REPORTS_PAGE,
    CB_EMPLOYEE_REPORT,
    employee_reports_menu,
)
from services.report_builder import (
    render_employee_summary,
    render_full_report,
    render_reports_list,
)
from services.report_service import summary_for_report
from utils import dates
from utils.access import IsAdmin

router = Router(name="reports")


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
        summary = await summary_for_report(report)
        if is_admin:
            await message.answer(
                render_full_report(summary, f"ID {report.employee_telegram_id}"),
                reply_markup=report_card_menu(report.id),
            )
        else:
            await message.answer(render_employee_summary(summary))


async def _send_reports_list(
    message: Message,
    page: int = 0,
    *,
    edit: bool = False,
) -> None:
    if message.from_user is None:
        return
    is_admin = config.is_admin(message.from_user.id)
    employee_id = None if is_admin else message.from_user.id
    total = await db.count_reports(employee_telegram_id=employee_id)
    pages = max(1, (total + REPORTS_PAGE_SIZE - 1) // REPORTS_PAGE_SIZE) if total else 1
    page = max(0, min(page, pages - 1))
    if not total:
        text = (
            "Сохраненных отчетов пока нет."
            if is_admin
            else "Вы еще не сохранили ни одного отчета."
        )
        if edit:
            await message.edit_text(text)
        else:
            await message.answer(text)
        return

    reports = await db.list_reports(
        limit=REPORTS_PAGE_SIZE,
        offset=page * REPORTS_PAGE_SIZE,
        employee_telegram_id=employee_id,
    )
    title = "Последние отчеты" if is_admin else "Ваши последние отчеты"
    text = render_reports_list(
        reports, title, page=page, total=total, page_size=REPORTS_PAGE_SIZE
    )
    markup = (
        reports_menu(reports, page=page, total=total)
        if is_admin
        else employee_reports_menu(reports, page=page, total=total)
    )
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


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


@router.callback_query(F.data.startswith(CB_REPORTS_PAGE), IsAdmin())
async def admin_reports_page(callback: CallbackQuery) -> None:
    raw = (callback.data or "")[len(CB_REPORTS_PAGE) :]
    page = int(raw) if raw.isdigit() else 0
    if callback.message is not None:
        await _send_reports_list(callback.message, page, edit=True)
    await callback.answer()


@router.callback_query(F.data.startswith(CB_EMP_REPORTS_PAGE))
async def employee_reports_page(callback: CallbackQuery) -> None:
    raw = (callback.data or "")[len(CB_EMP_REPORTS_PAGE) :]
    page = int(raw) if raw.isdigit() else 0
    if callback.message is not None:
        await _send_reports_list(callback.message, page, edit=True)
    await callback.answer()


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
    summary = await summary_for_report(report)
    if callback.message is not None:
        await callback.message.answer(render_employee_summary(summary))
    await callback.answer()
