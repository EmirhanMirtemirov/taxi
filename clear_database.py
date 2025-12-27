#!/usr/bin/env python3
"""
Скрипт для полной очистки базы данных
Удаляет всех пользователей и все объявления
"""

import asyncio
import logging
import time
from sqlalchemy import delete, select, func
from database.db import get_session, close_db
from database.models import (
    User, Post, Subscription, NotificationLog, 
    Rating, RatingRequest
)

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def clear_database():
    """Полная очистка базы данных"""
    
    logger.info("🚀 Начинаю очистку базы данных...")
    
    async with get_session() as session:
        try:
            # Подсчитываем количество записей перед удалением
            users_count = await session.scalar(select(func.count(User.id)))
            posts_count = await session.scalar(select(func.count(Post.id)))
            subscriptions_count = await session.scalar(select(func.count(Subscription.id)))
            notifications_count = await session.scalar(select(func.count(NotificationLog.id)))
            ratings_count = await session.scalar(select(func.count(Rating.id)))
            rating_requests_count = await session.scalar(select(func.count(RatingRequest.id)))
            
            logger.info(f"📊 Текущее состояние базы данных:")
            logger.info(f"   - Пользователей: {users_count}")
            logger.info(f"   - Объявлений: {posts_count}")
            logger.info(f"   - Подписок: {subscriptions_count}")
            logger.info(f"   - Уведомлений: {notifications_count}")
            logger.info(f"   - Оценок: {ratings_count}")
            logger.info(f"   - Запросов на оценку: {rating_requests_count}")
            
            # Удаляем в правильном порядке (сначала зависимые таблицы)
            logger.info("\n🗑️  Удаляю данные...")
            
            # 1. Удаляем логи уведомлений
            deleted_notifications = await session.execute(delete(NotificationLog))
            logger.info(f"   ✅ Удалено уведомлений: {deleted_notifications.rowcount}")
            
            # 2. Удаляем запросы на оценку
            deleted_rating_requests = await session.execute(delete(RatingRequest))
            logger.info(f"   ✅ Удалено запросов на оценку: {deleted_rating_requests.rowcount}")
            
            # 3. Удаляем оценки
            deleted_ratings = await session.execute(delete(Rating))
            logger.info(f"   ✅ Удалено оценок: {deleted_ratings.rowcount}")
            
            # 4. Удаляем подписки
            deleted_subscriptions = await session.execute(delete(Subscription))
            logger.info(f"   ✅ Удалено подписок: {deleted_subscriptions.rowcount}")
            
            # 5. Удаляем объявления
            deleted_posts = await session.execute(delete(Post))
            logger.info(f"   ✅ Удалено объявлений: {deleted_posts.rowcount}")
            
            # 6. Удаляем пользователей
            deleted_users = await session.execute(delete(User))
            logger.info(f"   ✅ Удалено пользователей: {deleted_users.rowcount}")
            
            # Коммитим все изменения
            await session.commit()
            
            logger.info("\n✅ База данных успешно очищена!")
            
        except Exception as e:
            logger.error(f"❌ Ошибка при очистке базы данных: {e}")
            await session.rollback()
            raise


async def main():
    """Главная функция"""
    try:
        await clear_database()
    finally:
        await close_db()


if __name__ == "__main__":
    print("⚠️  ВНИМАНИЕ: Этот скрипт удалит ВСЕ данные из базы!")
    print("   - Всех пользователей")
    print("   - Все объявления")
    print("   - Все подписки")
    print("   - Все уведомления")
    print("   - Все оценки")
    print("\nДля продолжения нажмите Ctrl+C, чтобы отменить")
    print("Или подождите 5 секунд...\n")
    
    try:
        time.sleep(5)
    except KeyboardInterrupt:
        print("\n❌ Отменено пользователем")
        exit(0)
    
    asyncio.run(main())

