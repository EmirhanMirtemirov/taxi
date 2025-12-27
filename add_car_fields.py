#!/usr/bin/env python3
"""
Скрипт для добавления полей car_photo_file_id и car_number в таблицу users
"""

import asyncio
import logging
from sqlalchemy import text
from database.db import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def add_car_fields():
    """Добавляет поля для фото и номера автомобиля"""
    
    logger.info("🚀 Начинаю миграцию...")
    
    async with engine.begin() as conn:
        try:
            # Проверяем, существуют ли уже поля
            check_query = text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'users' 
                AND column_name IN ('car_photo_file_id', 'car_number')
            """)
            result = await conn.execute(check_query)
            existing_columns = [row[0] for row in result.fetchall()]
            
            # Добавляем car_photo_file_id если его нет
            if 'car_photo_file_id' not in existing_columns:
                await conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN car_photo_file_id VARCHAR(255)
                """))
                logger.info("✅ Добавлено поле car_photo_file_id")
            else:
                logger.info("ℹ️  Поле car_photo_file_id уже существует")
            
            # Добавляем car_number если его нет
            if 'car_number' not in existing_columns:
                await conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN car_number VARCHAR(20)
                """))
                logger.info("✅ Добавлено поле car_number")
                
                # Добавляем уникальное ограничение
                try:
                    await conn.execute(text("""
                        CREATE UNIQUE INDEX idx_users_car_number_unique 
                        ON users(car_number) 
                        WHERE car_number IS NOT NULL
                    """))
                    logger.info("✅ Добавлено уникальное ограничение на car_number")
                except Exception as e:
                    logger.warning(f"⚠️  Не удалось добавить уникальное ограничение: {e}")
            else:
                logger.info("ℹ️  Поле car_number уже существует")
                
                # Проверяем, есть ли уже уникальное ограничение
                constraint_check = text("""
                    SELECT indexname 
                    FROM pg_indexes 
                    WHERE tablename = 'users' 
                    AND indexname = 'idx_users_car_number_unique'
                """)
                constraint_result = await conn.execute(constraint_check)
                if not constraint_result.fetchone():
                    try:
                        await conn.execute(text("""
                            CREATE UNIQUE INDEX idx_users_car_number_unique 
                            ON users(car_number) 
                            WHERE car_number IS NOT NULL
                        """))
                        logger.info("✅ Добавлено уникальное ограничение на car_number")
                    except Exception as e:
                        logger.warning(f"⚠️  Не удалось добавить уникальное ограничение: {e}")
            
            logger.info("✅ Миграция завершена успешно!")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при миграции: {e}")
            raise


async def main():
    try:
        await add_car_fields()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

