"""Роутеры бота. Порядок подключения важен, fallback — всегда последним."""

from __future__ import annotations

from aiogram import Router

from handlers import admin, common, employee, reports


def get_routers() -> list[Router]:
    return [
        common.router,
        admin.router,
        employee.router,
        reports.router,
        common.fallback_router,
    ]
