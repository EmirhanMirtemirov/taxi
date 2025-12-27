# database.py - Работа с базой данных SQLite
# Асинхронные операции через aiosqlite

import aiosqlite
from datetime import datetime, timedelta
from typing import Optional
from config import DATABASE_NAME, ORDER_LIFETIME_HOURS


async def init_db():
    """Инициализация базы данных и создание таблиц"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        # Таблица пользователей
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                telegram_id INTEGER UNIQUE NOT NULL,
                role TEXT NOT NULL,
                name TEXT NOT NULL,
                phone TEXT NOT NULL,
                car_model TEXT,
                car_number TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Таблица заявок
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                point_a TEXT NOT NULL,
                point_b TEXT NOT NULL,
                price INTEGER NOT NULL,
                message_id INTEGER,
                status TEXT DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        
        await db.commit()


# ==================== ОПЕРАЦИИ С ПОЛЬЗОВАТЕЛЯМИ ====================

async def get_user(telegram_id: int) -> Optional[dict]:
    """Получить пользователя по telegram_id"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", 
            (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_user(
    telegram_id: int,
    role: str,
    name: str,
    phone: str,
    car_model: str = None,
    car_number: str = None
) -> int:
    """Создать нового пользователя, вернуть его ID"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute(
            """INSERT INTO users (telegram_id, role, name, phone, car_model, car_number)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (telegram_id, role, name, phone, car_model, car_number)
        )
        await db.commit()
        return cursor.lastrowid


async def update_user(telegram_id: int, **kwargs) -> bool:
    """Обновить данные пользователя"""
    if not kwargs:
        return False
    
    # Формируем SET часть запроса
    set_parts = [f"{key} = ?" for key in kwargs.keys()]
    set_clause = ", ".join(set_parts)
    values = list(kwargs.values()) + [telegram_id]
    
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute(
            f"UPDATE users SET {set_clause} WHERE telegram_id = ?",
            values
        )
        await db.commit()
        return True


async def delete_user(telegram_id: int) -> bool:
    """Удалить пользователя"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute(
            "DELETE FROM users WHERE telegram_id = ?",
            (telegram_id,)
        )
        await db.commit()
        return True


# ==================== ОПЕРАЦИИ С ЗАЯВКАМИ ====================

async def get_active_order(telegram_id: int) -> Optional[dict]:
    """Получить активную заявку пользователя"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT o.*, u.name, u.phone, u.car_model, u.car_number
               FROM orders o
               JOIN users u ON o.user_id = u.id
               WHERE u.telegram_id = ? AND o.status = 'active'
               ORDER BY o.created_at DESC
               LIMIT 1""",
            (telegram_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_order_by_id(order_id: int) -> Optional[dict]:
    """Получить заявку по ID с данными пользователя"""
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT o.*, u.telegram_id, u.name, u.phone, u.car_model, u.car_number
               FROM orders o
               JOIN users u ON o.user_id = u.id
               WHERE o.id = ?""",
            (order_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_order(
    telegram_id: int,
    role: str,
    point_a: str,
    point_b: str,
    price: int,
    message_id: int = None
) -> int:
    """Создать новую заявку"""
    # Получаем user_id
    user = await get_user(telegram_id)
    if not user:
        raise ValueError("Пользователь не найден")
    
    # Вычисляем время истечения
    expires_at = datetime.utcnow() + timedelta(hours=ORDER_LIFETIME_HOURS)
    
    async with aiosqlite.connect(DATABASE_NAME) as db:
        cursor = await db.execute(
            """INSERT INTO orders (user_id, role, point_a, point_b, price, message_id, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user["id"], role, point_a, point_b, price, message_id, expires_at.isoformat())
        )
        await db.commit()
        return cursor.lastrowid


async def update_order(order_id: int, **kwargs) -> bool:
    """Обновить данные заявки"""
    if not kwargs:
        return False
    
    set_parts = [f"{key} = ?" for key in kwargs.keys()]
    set_clause = ", ".join(set_parts)
    values = list(kwargs.values()) + [order_id]
    
    async with aiosqlite.connect(DATABASE_NAME) as db:
        await db.execute(
            f"UPDATE orders SET {set_clause} WHERE id = ?",
            values
        )
        await db.commit()
        return True


async def cancel_order(order_id: int) -> bool:
    """Отменить заявку"""
    return await update_order(order_id, status="cancelled")


async def take_order(order_id: int) -> bool:
    """Пометить заявку как забронированную"""
    return await update_order(order_id, status="taken")


async def get_expired_orders() -> list:
    """Получить список истёкших активных заявок"""
    now = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DATABASE_NAME) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT o.*, u.telegram_id, u.name
               FROM orders o
               JOIN users u ON o.user_id = u.id
               WHERE o.status = 'active' AND o.expires_at < ?""",
            (now,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


async def expire_order(order_id: int) -> bool:
    """Пометить заявку как истёкшую"""
    return await update_order(order_id, status="expired")


async def get_user_orders_count(telegram_id: int) -> int:
    """Получить количество заявок пользователя"""
    user = await get_user(telegram_id)
    if not user:
        return 0
    
    async with aiosqlite.connect(DATABASE_NAME) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id = ?",
            (user["id"],)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

