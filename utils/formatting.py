"""Европейское форматирование чисел и разбор пользовательского ввода."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from config import config


def round_money(value: float, decimals: int = 2) -> float:
    """Округление до цента как в кассе: половинка всегда вверх."""
    quant = Decimal(1).scaleb(-decimals)
    return float(Decimal(str(float(value))).quantize(quant, rounding=ROUND_HALF_UP))


def format_amount(value: float, decimals: int = 2) -> str:
    """1234.5 -> '1234,50', 571.0 -> '571'."""
    rounded = round_money(value, decimals)
    text = f"{rounded:.{decimals}f}"
    if decimals > 0:
        whole, _, fraction = text.partition(".")
        if fraction.strip("0") == "":
            text = whole
    if text in ("-0", "-0,00"):
        text = "0"
    return text.replace(".", ",")


def format_money(value: float) -> str:
    """571.0 -> '571€', 13.28 -> '13,28€'."""
    return f"{format_amount(value, 2)}{config.currency}"


def format_quantity(value: int) -> str:
    return f"{int(value)} шт."


def format_upd(value: float) -> str:
    """1.71875 -> '1,72'."""
    return format_amount(value, 2)


def parse_int(text: str | None) -> int | None:
    """Целое неотрицательное число из текста пользователя."""
    if not text:
        return None
    cleaned = text.strip().replace(" ", "").replace("\u00a0", "")
    if not cleaned:
        return None
    try:
        value = int(cleaned)
    except ValueError:
        return None
    return value if value >= 0 else None


def parse_amount(text: str | None) -> float | None:
    """Сумма из текста пользователя: '571', '571,50', '571.50', '571 €'."""
    if not text:
        return None
    cleaned = (
        text.strip()
        .replace(" ", "")
        .replace("\u00a0", "")
        .replace(config.currency, "")
        .replace("€", "")
        .replace("eur", "")
        .replace("EUR", "")
        .replace(",", ".")
    )
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value if value >= 0 else None
