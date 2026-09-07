"""Работа с датами отчетов."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime

DB_DATE_FORMAT = "%Y-%m-%d"
DB_MONTH_FORMAT = "%Y-%m"

_USER_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y")


def today() -> date:
    return date.today()


def to_db(value: date) -> str:
    return value.strftime(DB_DATE_FORMAT)


def from_db(value: str) -> date:
    return datetime.strptime(value, DB_DATE_FORMAT).date()


def format_short(value: date | str) -> str:
    """'01.09' — как в шапке итогового отчета."""
    if isinstance(value, str):
        value = from_db(value)
    return value.strftime("%d.%m")


def format_full(value: date | str) -> str:
    """'01.09.2025'."""
    if isinstance(value, str):
        value = from_db(value)
    return value.strftime("%d.%m.%Y")


def month_key(value: date | str) -> str:
    """'2025-09' — ключ месяца для планов и месячной кассы."""
    if isinstance(value, str):
        value = from_db(value)
    return value.strftime(DB_MONTH_FORMAT)


def format_month(key: str) -> str:
    """'2025-09' -> '09.2025'."""
    return datetime.strptime(key, DB_MONTH_FORMAT).strftime("%m.%Y")


def days_in_month(value: date | str) -> int:
    if isinstance(value, str):
        value = from_db(value)
    return monthrange(value.year, value.month)[1]


def shift_month(value: date, months: int) -> date:
    """Первое число месяца, сдвинутого на `months` от даты."""
    total = value.year * 12 + (value.month - 1) + months
    return date(total // 12, total % 12 + 1, 1)


def parse_user_date(text: str | None) -> date | None:
    """Понимает '01.09', '01.09.2025', '1.9.25', '01/09' и т. п."""
    if not text:
        return None
    cleaned = text.strip().replace(" ", "")
    if not cleaned:
        return None
    for fmt in _USER_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    for fmt in ("%d.%m", "%d/%m", "%d-%m"):
        try:
            parsed = datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
        return parsed.replace(year=today().year)
    return None
