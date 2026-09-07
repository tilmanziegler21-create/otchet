"""Работа с SQLite (aiosqlite): схема, категории, отчеты."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

import aiosqlite

from config import config

ROLE_ADMIN = "admin"
ROLE_EMPLOYEE = "employee"

# Как считается «минус работникам» в городе.
SALARY_PERCENT = "percent"  # процент от дневного оборота
SALARY_FIXED = "fixed"  # фиксированная сумма за день
SALARY_MONTHLY = "monthly"  # фикс за месяц, в отчете делится на дни месяца
SALARY_KINDS = (SALARY_PERCENT, SALARY_FIXED, SALARY_MONTHLY)

# name, purchase_price, is_liquid
DEFAULT_CATEGORIES: tuple[tuple[str, float, int], ...] = (
    ("ELFLIQ", 0.0, 1),
    ("CHASER", 0.0, 1),
    ("HQD", 0.0, 0),
    ("VOZOL", 0.0, 0),
)

SCHEMA_SCRIPT = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    role        TEXT NOT NULL DEFAULT 'employee'
);

CREATE TABLE IF NOT EXISTS categories (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL UNIQUE,
    purchase_price REAL    NOT NULL DEFAULT 0,
    is_liquid      INTEGER NOT NULL DEFAULT 0,
    active         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS cities (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    salary_kind  TEXT    NOT NULL DEFAULT 'percent',
    salary_value REAL    NOT NULL DEFAULT 0,
    active       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS monthly_plans (
    city_id INTEGER NOT NULL REFERENCES cities(id),
    month   TEXT    NOT NULL,
    amount  REAL    NOT NULL DEFAULT 0,
    PRIMARY KEY (city_id, month)
);

CREATE TABLE IF NOT EXISTS daily_reports (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    date                  TEXT    NOT NULL,
    city_id               INTEGER REFERENCES cities(id),
    employee_telegram_id  INTEGER NOT NULL,
    customers_count       INTEGER NOT NULL DEFAULT 0,
    salary_kind_snapshot  TEXT    NOT NULL DEFAULT 'percent',
    salary_value_snapshot REAL    NOT NULL DEFAULT 0,
    bonus_snapshot        REAL    NOT NULL DEFAULT 0,
    plan_snapshot         REAL    NOT NULL DEFAULT 0,
    touches               INTEGER NOT NULL DEFAULT 0,
    replies               INTEGER NOT NULL DEFAULT 0,
    purchases             INTEGER NOT NULL DEFAULT 0,
    extra_revenue         REAL    NOT NULL DEFAULT 0,
    created_at            TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports(date);

CREATE TABLE IF NOT EXISTS daily_report_items (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id               INTEGER NOT NULL REFERENCES daily_reports(id) ON DELETE CASCADE,
    category_id             INTEGER NOT NULL REFERENCES categories(id),
    quantity                INTEGER NOT NULL DEFAULT 0,
    revenue                 REAL    NOT NULL DEFAULT 0,
    purchase_price_snapshot REAL    NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_report_items_report ON daily_report_items(report_id);
"""


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    purchase_price: float
    is_liquid: bool
    active: bool


@dataclass(frozen=True)
class City:
    id: int
    name: str
    salary_kind: str
    salary_value: float
    active: bool


@dataclass(frozen=True)
class ReportItem:
    category_id: int
    name: str
    is_liquid: bool
    quantity: int
    revenue: float
    purchase_price_snapshot: float


@dataclass(frozen=True)
class Report:
    id: int
    date: str
    city_id: int | None
    city_name: str | None
    employee_telegram_id: int
    customers_count: int
    salary_kind: str
    salary_value: float
    bonus: float
    plan: float
    touches: int
    replies: int
    purchases: int
    extra_revenue: float
    created_at: str
    items: tuple[ReportItem, ...]


@dataclass(frozen=True)
class ReportBrief:
    id: int
    date: str
    city_name: str | None
    employee_telegram_id: int
    customers_count: int
    total_quantity: int
    total_revenue: float


def _connect() -> aiosqlite.Connection:
    connection = aiosqlite.connect(config.db_path)
    return connection


async def _columns(db: aiosqlite.Connection, table: str) -> set[str]:
    cursor = await db.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in await cursor.fetchall()}


async def _migrate(db: aiosqlite.Connection) -> None:
    """Догоняет схему в базах, созданных предыдущими версиями бота."""
    reports = await _columns(db, "daily_reports")
    if "city_id" not in reports:
        await db.execute(
            "ALTER TABLE daily_reports ADD COLUMN city_id INTEGER REFERENCES cities(id)"
        )
    if "salary_kind_snapshot" not in reports:
        await db.execute(
            "ALTER TABLE daily_reports ADD COLUMN salary_kind_snapshot TEXT "
            "NOT NULL DEFAULT 'percent'"
        )
    if "salary_value_snapshot" not in reports:
        await db.execute(
            "ALTER TABLE daily_reports ADD COLUMN salary_value_snapshot REAL "
            "NOT NULL DEFAULT 0"
        )
    if "bonus_snapshot" not in reports:
        await db.execute(
            "ALTER TABLE daily_reports ADD COLUMN bonus_snapshot REAL "
            "NOT NULL DEFAULT 0"
        )
    if "plan_snapshot" not in reports:
        await db.execute(
            "ALTER TABLE daily_reports ADD COLUMN plan_snapshot REAL "
            "NOT NULL DEFAULT 0"
        )
    for column, kind in (
        ("touches", "INTEGER"),
        ("replies", "INTEGER"),
        ("purchases", "INTEGER"),
        ("extra_revenue", "REAL"),
    ):
        if column not in reports:
            await db.execute(
                f"ALTER TABLE daily_reports ADD COLUMN {column} {kind} "
                "NOT NULL DEFAULT 0"
            )

    cities = await _columns(db, "cities")
    if "salary_kind" not in cities:
        await db.execute(
            "ALTER TABLE cities ADD COLUMN salary_kind TEXT NOT NULL DEFAULT 'percent'"
        )
    if "salary_value" not in cities:
        await db.execute(
            "ALTER TABLE cities ADD COLUMN salary_value REAL NOT NULL DEFAULT 0"
        )


async def init_db() -> None:
    """Создает схему, добавляет категории по умолчанию и синхронизирует админов."""
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.executescript(SCHEMA_SCRIPT)
        await _migrate(db)
        for name, price, is_liquid in DEFAULT_CATEGORIES:
            await db.execute(
                "INSERT OR IGNORE INTO categories (name, purchase_price, is_liquid, active) "
                "VALUES (?, ?, ?, 1)",
                (name, price, is_liquid),
            )
        for admin_id in config.admin_ids:
            await db.execute(
                "INSERT INTO users (telegram_id, role) VALUES (?, ?) "
                "ON CONFLICT(telegram_id) DO UPDATE SET role = excluded.role",
                (admin_id, ROLE_ADMIN),
            )
        await db.commit()


# ---------------------------------------------------------------- users


async def register_user(telegram_id: int) -> str:
    """Сохраняет пользователя и возвращает его роль."""
    role = ROLE_ADMIN if config.is_admin(telegram_id) else ROLE_EMPLOYEE
    async with _connect() as db:
        await db.execute(
            "INSERT INTO users (telegram_id, role) VALUES (?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET role = excluded.role",
            (telegram_id, role),
        )
        await db.commit()
    return role


async def get_user_role(telegram_id: int) -> str | None:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT role FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
    return row["role"] if row else None


# ----------------------------------------------------------- categories


def _category_from_row(row: aiosqlite.Row) -> Category:
    return Category(
        id=row["id"],
        name=row["name"],
        purchase_price=float(row["purchase_price"]),
        is_liquid=bool(row["is_liquid"]),
        active=bool(row["active"]),
    )


async def get_categories(only_active: bool = True) -> list[Category]:
    query = "SELECT id, name, purchase_price, is_liquid, active FROM categories"
    if only_active:
        query += " WHERE active = 1"
    query += " ORDER BY id"
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query)
        rows = await cursor.fetchall()
    return [_category_from_row(row) for row in rows]


async def get_category(category_id: int) -> Category | None:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, purchase_price, is_liquid, active FROM categories WHERE id = ?",
            (category_id,),
        )
        row = await cursor.fetchone()
    return _category_from_row(row) if row else None


async def get_category_by_name(name: str) -> Category | None:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, name, purchase_price, is_liquid, active FROM categories "
            "WHERE name = ? COLLATE NOCASE",
            (name,),
        )
        row = await cursor.fetchone()
    return _category_from_row(row) if row else None


async def add_category(name: str, purchase_price: float, is_liquid: bool) -> int:
    async with _connect() as db:
        cursor = await db.execute(
            "INSERT INTO categories (name, purchase_price, is_liquid, active) VALUES (?, ?, ?, 1)",
            (name, float(purchase_price), int(is_liquid)),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def set_purchase_price(category_id: int, purchase_price: float) -> None:
    async with _connect() as db:
        await db.execute(
            "UPDATE categories SET purchase_price = ? WHERE id = ?",
            (float(purchase_price), category_id),
        )
        await db.commit()


# --------------------------------------------------------------- cities


def _city_from_row(row: aiosqlite.Row) -> City:
    return City(
        id=row["id"],
        name=row["name"],
        salary_kind=row["salary_kind"],
        salary_value=float(row["salary_value"]),
        active=bool(row["active"]),
    )


_CITY_SELECT = "SELECT id, name, salary_kind, salary_value, active FROM cities"


async def get_cities(only_active: bool = True) -> list[City]:
    query = _CITY_SELECT
    if only_active:
        query += " WHERE active = 1"
    query += " ORDER BY name COLLATE NOCASE"
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query)
        rows = await cursor.fetchall()
    return [_city_from_row(row) for row in rows]


async def get_city(city_id: int) -> City | None:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(_CITY_SELECT + " WHERE id = ?", (city_id,))
        row = await cursor.fetchone()
    return _city_from_row(row) if row else None


async def get_city_by_name(name: str) -> City | None:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            _CITY_SELECT + " WHERE name = ? COLLATE NOCASE", (name,)
        )
        row = await cursor.fetchone()
    return _city_from_row(row) if row else None


async def add_city(name: str) -> int:
    async with _connect() as db:
        cursor = await db.execute(
            "INSERT INTO cities (name, active) VALUES (?, 1)", (name,)
        )
        await db.commit()
        return int(cursor.lastrowid)


async def set_city_salary(city_id: int, salary_kind: str, salary_value: float) -> None:
    """Ставка «минус работникам»: процент, фикс за день или фикс за месяц."""
    if salary_kind not in SALARY_KINDS:
        raise ValueError(f"Неизвестный тип ставки: {salary_kind}")
    async with _connect() as db:
        await db.execute(
            "UPDATE cities SET salary_kind = ?, salary_value = ? WHERE id = ?",
            (salary_kind, float(salary_value), city_id),
        )
        await db.commit()


async def set_city_active(city_id: int, active: bool) -> None:
    async with _connect() as db:
        await db.execute(
            "UPDATE cities SET active = ? WHERE id = ?", (int(active), city_id)
        )
        await db.commit()


# --------------------------------------------------- планы и месячная касса


async def get_monthly_plan(city_id: int, month: str) -> float:
    """План города на месяц ('2025-09'). 0 — план не задан, бонус не считается."""
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT amount FROM monthly_plans WHERE city_id = ? AND month = ?",
            (city_id, month),
        )
        row = await cursor.fetchone()
    return float(row[0]) if row else 0.0


async def set_monthly_plan(city_id: int, month: str, amount: float) -> None:
    async with _connect() as db:
        if amount <= 0:
            await db.execute(
                "DELETE FROM monthly_plans WHERE city_id = ? AND month = ?",
                (city_id, month),
            )
        else:
            await db.execute(
                "INSERT INTO monthly_plans (city_id, month, amount) VALUES (?, ?, ?) "
                "ON CONFLICT(city_id, month) DO UPDATE SET amount = excluded.amount",
                (city_id, month, float(amount)),
            )
        await db.commit()


async def get_month_revenue(
    city_id: int, month: str, exclude_report_id: int | None = None
) -> float:
    """Касса города с начала месяца по сохраненным отчетам."""
    query = (
        "SELECT COALESCE(SUM(i.revenue), 0) "
        "FROM daily_reports AS r "
        "JOIN daily_report_items AS i ON i.report_id = r.id "
        "WHERE r.city_id = ? AND r.date LIKE ?"
    )
    params: list[object] = [city_id, f"{month}-%"]
    if exclude_report_id is not None:
        query += " AND r.id != ?"
        params.append(exclude_report_id)
    async with _connect() as db:
        cursor = await db.execute(query, params)
        row = await cursor.fetchone()
    return float(row[0]) if row else 0.0


# -------------------------------------------------------------- reports


async def save_report(
    report_date: str,
    city_id: int | None,
    employee_telegram_id: int,
    customers_count: int,
    salary_kind: str,
    salary_value: float,
    bonus: float,
    plan: float,
    items: Sequence[tuple[int, int, float, float]],
    touches: int = 0,
    replies: int = 0,
    purchases: int = 0,
    extra_revenue: float = 0.0,
) -> int:
    """items: (category_id, quantity, revenue, purchase_price_snapshot)."""
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cursor = await db.execute(
            "INSERT INTO daily_reports "
            "(date, city_id, employee_telegram_id, customers_count, "
            " salary_kind_snapshot, salary_value_snapshot, bonus_snapshot, "
            " plan_snapshot, touches, replies, purchases, extra_revenue, "
            " created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                report_date,
                city_id,
                employee_telegram_id,
                customers_count,
                salary_kind,
                float(salary_value),
                float(bonus),
                float(plan),
                int(touches),
                int(replies),
                int(purchases),
                float(extra_revenue),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        report_id = int(cursor.lastrowid)
        await db.executemany(
            "INSERT INTO daily_report_items "
            "(report_id, category_id, quantity, revenue, purchase_price_snapshot) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (report_id, category_id, int(quantity), float(revenue), float(price))
                for category_id, quantity, revenue, price in items
            ],
        )
        await db.commit()
    return report_id


async def _fetch_report(db: aiosqlite.Connection, row: aiosqlite.Row) -> Report:
    cursor = await db.execute(
        "SELECT i.category_id, c.name, c.is_liquid, i.quantity, i.revenue, "
        "       i.purchase_price_snapshot "
        "FROM daily_report_items AS i "
        "JOIN categories AS c ON c.id = i.category_id "
        "WHERE i.report_id = ? ORDER BY i.category_id",
        (row["id"],),
    )
    item_rows = await cursor.fetchall()
    items = tuple(
        ReportItem(
            category_id=item["category_id"],
            name=item["name"],
            is_liquid=bool(item["is_liquid"]),
            quantity=int(item["quantity"]),
            revenue=float(item["revenue"]),
            purchase_price_snapshot=float(item["purchase_price_snapshot"]),
        )
        for item in item_rows
    )
    return Report(
        id=row["id"],
        date=row["date"],
        city_id=row["city_id"],
        city_name=row["city_name"],
        employee_telegram_id=row["employee_telegram_id"],
        customers_count=int(row["customers_count"]),
        salary_kind=row["salary_kind_snapshot"] or SALARY_PERCENT,
        salary_value=float(row["salary_value_snapshot"] or 0),
        bonus=float(row["bonus_snapshot"] or 0),
        plan=float(row["plan_snapshot"] or 0),
        touches=int(row["touches"] or 0),
        replies=int(row["replies"] or 0),
        purchases=int(row["purchases"] or 0),
        extra_revenue=float(row["extra_revenue"] or 0),
        created_at=row["created_at"],
        items=items,
    )


_REPORT_SELECT = (
    "SELECT r.id, r.date, r.city_id, ci.name AS city_name, "
    "       r.employee_telegram_id, r.customers_count, "
    "       r.salary_kind_snapshot, r.salary_value_snapshot, "
    "       r.bonus_snapshot, r.plan_snapshot, "
    "       r.touches, r.replies, r.purchases, r.extra_revenue, r.created_at "
    "FROM daily_reports AS r "
    "LEFT JOIN cities AS ci ON ci.id = r.city_id "
)


async def get_report(report_id: int) -> Report | None:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(_REPORT_SELECT + "WHERE r.id = ?", (report_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return await _fetch_report(db, row)


async def get_reports_by_date(
    report_date: str, employee_telegram_id: int | None = None
) -> list[Report]:
    """Все отчеты за дату — по одному на город."""
    query = _REPORT_SELECT + "WHERE r.date = ?"
    params: list[object] = [report_date]
    if employee_telegram_id is not None:
        query += " AND r.employee_telegram_id = ?"
        params.append(employee_telegram_id)
    query += " ORDER BY ci.name COLLATE NOCASE, r.id"
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [await _fetch_report(db, row) for row in rows]


async def get_reports_between(
    start_date: str, end_date: str, city_id: int | None = None
) -> list[Report]:
    """Отчеты за период включительно — основа недельной и месячной сводки."""
    query = _REPORT_SELECT + "WHERE r.date BETWEEN ? AND ?"
    params: list[object] = [start_date, end_date]
    if city_id is not None:
        query += " AND r.city_id = ?"
        params.append(city_id)
    query += " ORDER BY r.date, r.id"
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [await _fetch_report(db, row) for row in rows]


async def count_reports_by_date(report_date: str, city_id: int | None = None) -> int:
    query = "SELECT COUNT(*) FROM daily_reports WHERE date = ?"
    params: list[object] = [report_date]
    if city_id is not None:
        query += " AND city_id = ?"
        params.append(city_id)
    async with _connect() as db:
        cursor = await db.execute(query, params)
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def list_reports(
    limit: int = 10,
    offset: int = 0,
    employee_telegram_id: int | None = None,
    city_id: int | None = None,
) -> list[ReportBrief]:
    query = (
        "SELECT r.id, r.date, ci.name AS city_name, r.employee_telegram_id, "
        "       r.customers_count, "
        "       COALESCE(SUM(i.quantity), 0) AS total_quantity, "
        "       COALESCE(SUM(i.revenue), 0)  AS total_revenue "
        "FROM daily_reports AS r "
        "LEFT JOIN cities AS ci ON ci.id = r.city_id "
        "LEFT JOIN daily_report_items AS i ON i.report_id = r.id "
    )
    conditions: list[str] = []
    params: list[object] = []
    if employee_telegram_id is not None:
        conditions.append("r.employee_telegram_id = ?")
        params.append(employee_telegram_id)
    if city_id is not None:
        conditions.append("r.city_id = ?")
        params.append(city_id)
    if conditions:
        query += "WHERE " + " AND ".join(conditions) + " "
    query += "GROUP BY r.id ORDER BY r.date DESC, r.id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
    return [
        ReportBrief(
            id=row["id"],
            date=row["date"],
            city_name=row["city_name"],
            employee_telegram_id=row["employee_telegram_id"],
            customers_count=int(row["customers_count"]),
            total_quantity=int(row["total_quantity"]),
            total_revenue=float(row["total_revenue"]),
        )
        for row in rows
    ]
