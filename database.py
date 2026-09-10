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

# Доп. расход города помимо курьеров — в чистую, не в UPD.
EXPENSE_NONE = "none"
EXPENSE_FIXED = "fixed"
EXPENSE_MONTHLY = "monthly"
EXPENSE_KINDS = (EXPENSE_NONE, EXPENSE_FIXED, EXPENSE_MONTHLY)

# Три общие копилки: накапливаются из отчетов, снимаются выплатой.
POT_MANAGER = "manager"
POT_CARLGAUSS = "carlgauss"
POT_REMAINDER = "remainder"
POTS = (POT_MANAGER, POT_CARLGAUSS, POT_REMAINDER)
POT_TITLES = {
    POT_MANAGER: "Менеджеру",
    POT_CARLGAUSS: "CARLGAUSS",
    POT_REMAINDER: "Остаток",
}

# Группы товаров: определяют порядок в отчете и то, какие вопросы задавать.
GROUP_LIQUID = "liquid"
GROUP_DEVICE = "device"
GROUP_POD = "pod"
GROUP_CARTRIDGE = "cartridge"
GROUP_SET = "set"

# Порядок ключей = порядок групп в отчете и при заполнении.
GROUP_TITLES: dict[str, str] = {
    GROUP_LIQUID: "Жидкости",
    GROUP_DEVICE: "Электронки",
    GROUP_POD: "Поды",
    GROUP_CARTRIDGE: "Картриджи",
    GROUP_SET: "Наборы",
}
GROUPS = tuple(GROUP_TITLES)

# Клиентов (а значит и UPD) спрашиваем только по этим группам.
GROUPS_WITH_CUSTOMERS = (GROUP_LIQUID, GROUP_DEVICE)

# name, purchase_price, group_key
DEFAULT_CATEGORIES: tuple[tuple[str, float, str], ...] = (
    ("ELFLIQ", 0.0, GROUP_LIQUID),
    ("CHASER", 0.0, GROUP_LIQUID),
    ("HQD", 0.0, GROUP_LIQUID),
    ("VOZOL", 0.0, GROUP_LIQUID),
    ("ELFBAR RAYA D3 25.000", 0.0, GROUP_DEVICE),
    ("ELFBAR NIC KING", 0.0, GROUP_DEVICE),
    ("ELFBAR SOUR KING", 0.0, GROUP_DEVICE),
    ("ELFBAR SWEET KING", 0.0, GROUP_DEVICE),
    ("ELFBAR DUKE 30.000", 0.0, GROUP_DEVICE),
    ("ELFBAR GH 33.000", 0.0, GROUP_DEVICE),
    ("ELFBAR 40.000", 0.0, GROUP_DEVICE),
    ("VOZOL 40.000", 0.0, GROUP_DEVICE),
    ("VOZOL 50.000", 0.0, GROUP_DEVICE),
    ("WAKA 60.000", 0.0, GROUP_DEVICE),
    ("XROS 5 MINI", 0.0, GROUP_POD),
    ("Картридж 0.6", 0.0, GROUP_CARTRIDGE),
    ("Картридж 0.8", 0.0, GROUP_CARTRIDGE),
    ("Картридж 0.4", 0.0, GROUP_CARTRIDGE),
    ("Под + 2 жижи (50€)", 0.0, GROUP_SET),
    ("2 пода + 4 жижи (90€)", 0.0, GROUP_SET),
    ("2 картриджа + 1 жидкость (25€)", 0.0, GROUP_SET),
    ("4 картриджа + 2 жижи (45€)", 0.0, GROUP_SET),
    ("Под + 2 жижи + 2 картриджа (60€)", 0.0, GROUP_SET),
    ("Под + 4 жидкости (70€)", 0.0, GROUP_SET),
    ("Под + 4 жидкости + 4 картриджа (90€)", 0.0, GROUP_SET),
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
    group_key      TEXT    NOT NULL DEFAULT 'liquid',
    active         INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS cities (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL UNIQUE,
    salary_kind    TEXT    NOT NULL DEFAULT 'percent',
    salary_value   REAL    NOT NULL DEFAULT 0,
    expense_kind   TEXT    NOT NULL DEFAULT 'none',
    expense_value  REAL    NOT NULL DEFAULT 0,
    active         INTEGER NOT NULL DEFAULT 1
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
    extra_revenue          REAL    NOT NULL DEFAULT 0,
    expense_kind_snapshot  TEXT    NOT NULL DEFAULT 'none',
    expense_value_snapshot REAL    NOT NULL DEFAULT 0,
    created_at             TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS payouts (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    pot                TEXT    NOT NULL,
    amount             REAL    NOT NULL,
    admin_telegram_id  INTEGER NOT NULL,
    created_at         TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_daily_reports_date ON daily_reports(date);

CREATE TABLE IF NOT EXISTS daily_report_items (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id               INTEGER NOT NULL REFERENCES daily_reports(id) ON DELETE CASCADE,
    category_id             INTEGER NOT NULL REFERENCES categories(id),
    quantity                INTEGER NOT NULL DEFAULT 0,
    revenue                 REAL    NOT NULL DEFAULT 0,
    purchase_price_snapshot REAL    NOT NULL DEFAULT 0,
    customers_count         INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_report_items_report ON daily_report_items(report_id);
"""


@dataclass(frozen=True)
class Category:
    id: int
    name: str
    purchase_price: float
    is_liquid: bool
    group_key: str
    active: bool

    @property
    def group_title(self) -> str:
        return GROUP_TITLES.get(self.group_key, self.group_key)

    @property
    def needs_customers(self) -> bool:
        """По подам, картриджам и наборам клиентов не спрашиваем."""
        return self.group_key in GROUPS_WITH_CUSTOMERS


@dataclass(frozen=True)
class City:
    id: int
    name: str
    salary_kind: str
    salary_value: float
    expense_kind: str
    expense_value: float
    active: bool


@dataclass(frozen=True)
class ReportItem:
    category_id: int
    name: str
    is_liquid: bool
    group_key: str
    quantity: int
    revenue: float
    purchase_price_snapshot: float
    customers_count: int


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
    expense_kind: str
    expense_value: float
    created_at: str
    items: tuple[ReportItem, ...]


@dataclass(frozen=True)
class Payout:
    id: int
    pot: str
    amount: float
    admin_telegram_id: int
    created_at: str

    @property
    def title(self) -> str:
        return POT_TITLES.get(self.pot, self.pot)


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

    items = await _columns(db, "daily_report_items")
    if "customers_count" not in items:
        await db.execute(
            "ALTER TABLE daily_report_items ADD COLUMN customers_count INTEGER "
            "NOT NULL DEFAULT 0"
        )

    categories = await _columns(db, "categories")
    if "group_key" not in categories:
        await db.execute(
            "ALTER TABLE categories ADD COLUMN group_key TEXT NOT NULL DEFAULT 'liquid'"
        )
        # Позиции из старых версий: известные раскладываем по каталогу,
        # остальные считаем электронками — жидкости там были только штатные.
        known = {name: group for name, _, group in DEFAULT_CATEGORIES}
        await db.execute(
            "UPDATE categories SET group_key = ?", (GROUP_DEVICE,)
        )
        for name, group in known.items():
            await db.execute(
                "UPDATE categories SET group_key = ? WHERE name = ? COLLATE NOCASE",
                (group, name),
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
    if "expense_kind" not in cities:
        await db.execute(
            "ALTER TABLE cities ADD COLUMN expense_kind TEXT NOT NULL DEFAULT 'none'"
        )
    if "expense_value" not in cities:
        await db.execute(
            "ALTER TABLE cities ADD COLUMN expense_value REAL NOT NULL DEFAULT 0"
        )

    if "expense_kind_snapshot" not in reports:
        await db.execute(
            "ALTER TABLE daily_reports ADD COLUMN expense_kind_snapshot TEXT "
            "NOT NULL DEFAULT 'none'"
        )
    if "expense_value_snapshot" not in reports:
        await db.execute(
            "ALTER TABLE daily_reports ADD COLUMN expense_value_snapshot REAL "
            "NOT NULL DEFAULT 0"
        )

    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS payouts (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            pot                TEXT    NOT NULL,
            amount             REAL    NOT NULL,
            admin_telegram_id  INTEGER NOT NULL,
            created_at         TEXT    NOT NULL
        )
        """
    )


class StorageError(RuntimeError):
    """Каталог из DB_PATH недоступен для записи — чаще всего не смонтирован диск."""


def _prepare_storage() -> None:
    folder = config.db_path.parent
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise StorageError(
            f"Каталог {folder} недоступен для записи ({error.strerror}). "
            f"DB_PATH={config.db_path}. На Render проверьте, что подключен диск "
            f"с Mount Path {folder}, либо укажите другой DB_PATH."
        ) from error


async def init_db() -> None:
    """Создает схему, добавляет категории по умолчанию и синхронизирует админов."""
    _prepare_storage()
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.executescript(SCHEMA_SCRIPT)
        await _migrate(db)
        for name, price, group_key in DEFAULT_CATEGORIES:
            await db.execute(
                "INSERT OR IGNORE INTO categories "
                "(name, purchase_price, is_liquid, group_key, active) VALUES (?, ?, ?, ?, 1)",
                (name, price, int(group_key == GROUP_LIQUID), group_key),
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


CATEGORY_FIELDS = "id, name, purchase_price, is_liquid, group_key, active"


def _group_order(group_column: str, id_column: str) -> str:
    """ORDER BY, который выстраивает позиции группами как в GROUP_TITLES."""
    cases = " ".join(
        f"WHEN '{key}' THEN {index}" for index, key in enumerate(GROUPS)
    )
    return (
        f"ORDER BY CASE {group_column} {cases} ELSE {len(GROUPS)} END, {id_column}"
    )


CATEGORY_ORDER = _group_order("group_key", "id")


def _category_from_row(row: aiosqlite.Row) -> Category:
    group_key = row["group_key"] or GROUP_LIQUID
    return Category(
        id=row["id"],
        name=row["name"],
        purchase_price=float(row["purchase_price"]),
        # Жидкость определяется группой: только она идет в UPD и «все жидкости».
        is_liquid=group_key == GROUP_LIQUID,
        group_key=group_key,
        active=bool(row["active"]),
    )


async def get_categories(only_active: bool = True) -> list[Category]:
    query = f"SELECT {CATEGORY_FIELDS} FROM categories"
    if only_active:
        query += " WHERE active = 1"
    query += f" {CATEGORY_ORDER}"
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query)
        rows = await cursor.fetchall()
    return [_category_from_row(row) for row in rows]


async def get_category(category_id: int) -> Category | None:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT {CATEGORY_FIELDS} FROM categories WHERE id = ?",
            (category_id,),
        )
        row = await cursor.fetchone()
    return _category_from_row(row) if row else None


async def get_category_by_name(name: str) -> Category | None:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT {CATEGORY_FIELDS} FROM categories WHERE name = ? COLLATE NOCASE",
            (name,),
        )
        row = await cursor.fetchone()
    return _category_from_row(row) if row else None


async def add_category(name: str, purchase_price: float, group_key: str) -> int:
    async with _connect() as db:
        cursor = await db.execute(
            "INSERT INTO categories (name, purchase_price, is_liquid, group_key, active) "
            "VALUES (?, ?, ?, ?, 1)",
            (
                name,
                float(purchase_price),
                int(group_key == GROUP_LIQUID),
                group_key,
            ),
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
        expense_kind=row["expense_kind"] or EXPENSE_NONE,
        expense_value=float(row["expense_value"] or 0),
        active=bool(row["active"]),
    )


_CITY_SELECT = (
    "SELECT id, name, salary_kind, salary_value, expense_kind, expense_value, "
    "active FROM cities"
)


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


async def set_city_expense(
    city_id: int, expense_kind: str, expense_value: float
) -> None:
    """Доп. расход города: нет, фикс за день или фикс за месяц."""
    if expense_kind not in EXPENSE_KINDS:
        raise ValueError(f"Неизвестный тип расхода: {expense_kind}")
    if expense_kind == EXPENSE_NONE:
        expense_value = 0.0
    async with _connect() as db:
        await db.execute(
            "UPDATE cities SET expense_kind = ?, expense_value = ? WHERE id = ?",
            (expense_kind, float(expense_value), city_id),
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
    items: Sequence[tuple[int, int, float, float, int]],
    touches: int = 0,
    replies: int = 0,
    purchases: int = 0,
    extra_revenue: float = 0.0,
    expense_kind: str = EXPENSE_NONE,
    expense_value: float = 0.0,
) -> int:
    """items: (category_id, quantity, revenue, purchase_price, customers_count)."""
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys = ON")
        cursor = await db.execute(
            "INSERT INTO daily_reports "
            "(date, city_id, employee_telegram_id, customers_count, "
            " salary_kind_snapshot, salary_value_snapshot, bonus_snapshot, "
            " plan_snapshot, touches, replies, purchases, extra_revenue, "
            " expense_kind_snapshot, expense_value_snapshot, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                expense_kind,
                float(expense_value),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        report_id = int(cursor.lastrowid)
        await db.executemany(
            "INSERT INTO daily_report_items "
            "(report_id, category_id, quantity, revenue, purchase_price_snapshot, "
            " customers_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    report_id,
                    category_id,
                    int(quantity),
                    float(revenue),
                    float(price),
                    int(customers),
                )
                for category_id, quantity, revenue, price, customers in items
            ],
        )
        await db.commit()
    return report_id


async def _fetch_report(db: aiosqlite.Connection, row: aiosqlite.Row) -> Report:
    cursor = await db.execute(
        "SELECT i.category_id, c.name, c.group_key, i.quantity, i.revenue, "
        "       i.purchase_price_snapshot, i.customers_count "
        "FROM daily_report_items AS i "
        "JOIN categories AS c ON c.id = i.category_id "
        f"WHERE i.report_id = ? {_group_order('c.group_key', 'i.category_id')}",
        (row["id"],),
    )
    item_rows = await cursor.fetchall()
    items = tuple(
        ReportItem(
            category_id=item["category_id"],
            name=item["name"],
            is_liquid=(item["group_key"] or GROUP_LIQUID) == GROUP_LIQUID,
            group_key=item["group_key"] or GROUP_LIQUID,
            quantity=int(item["quantity"]),
            revenue=float(item["revenue"]),
            purchase_price_snapshot=float(item["purchase_price_snapshot"]),
            customers_count=int(item["customers_count"] or 0),
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
        expense_kind=(
            row["expense_kind_snapshot"]
            if "expense_kind_snapshot" in row.keys()
            else EXPENSE_NONE
        )
        or EXPENSE_NONE,
        expense_value=float(
            row["expense_value_snapshot"]
            if "expense_value_snapshot" in row.keys()
            else 0
        )
        or 0,
        created_at=row["created_at"],
        items=items,
    )


_REPORT_SELECT = (
    "SELECT r.id, r.date, r.city_id, ci.name AS city_name, "
    "       r.employee_telegram_id, r.customers_count, "
    "       r.salary_kind_snapshot, r.salary_value_snapshot, "
    "       r.bonus_snapshot, r.plan_snapshot, "
    "       r.touches, r.replies, r.purchases, r.extra_revenue, "
    "       r.expense_kind_snapshot, r.expense_value_snapshot, r.created_at "
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


async def delete_report(report_id: int) -> bool:
    """Удаляет отчет и его позиции. False — такого отчета уже нет."""
    async with _connect() as db:
        await db.execute("PRAGMA foreign_keys = ON")
        await db.execute(
            "DELETE FROM daily_report_items WHERE report_id = ?", (report_id,)
        )
        cursor = await db.execute(
            "DELETE FROM daily_reports WHERE id = ?", (report_id,)
        )
        await db.commit()
        return cursor.rowcount > 0


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


async def count_reports() -> int:
    """Всего отчетов в базе — для подписи к бэкапу."""
    async with _connect() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM daily_reports")
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


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


async def get_all_reports() -> list[Report]:
    """Все дневные отчеты — из них собирается накопительная касса."""
    return await get_reports_between("0001-01-01", "9999-12-31")


async def add_payout(pot: str, amount: float, admin_telegram_id: int) -> int:
    if pot not in POTS:
        raise ValueError(f"Неизвестная копилка: {pot}")
    async with _connect() as db:
        cursor = await db.execute(
            "INSERT INTO payouts (pot, amount, admin_telegram_id, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                pot,
                float(amount),
                admin_telegram_id,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def sum_payouts() -> dict[str, float]:
    """Сколько уже выплатили из каждой копилки."""
    totals = {pot: 0.0 for pot in POTS}
    async with _connect() as db:
        cursor = await db.execute(
            "SELECT pot, COALESCE(SUM(amount), 0) FROM payouts GROUP BY pot"
        )
        for pot, amount in await cursor.fetchall():
            if pot in totals:
                totals[pot] = float(amount)
    return totals


async def list_payouts(limit: int = 10) -> list[Payout]:
    async with _connect() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, pot, amount, admin_telegram_id, created_at "
            "FROM payouts ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [
        Payout(
            id=row["id"],
            pot=row["pot"],
            amount=float(row["amount"]),
            admin_telegram_id=row["admin_telegram_id"],
            created_at=row["created_at"],
        )
        for row in rows
    ]
