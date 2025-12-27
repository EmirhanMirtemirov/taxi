# workers/expiration.py - Фоновый воркер для деактивации истёкших объявлений
# Проверяет каждую минуту и деактивирует объявления

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot
from sqlalchemy import select, update
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import EXPIRATION_CHECK_INTERVAL, BOT_TOKEN
from database.db import get_session
from database.models import Post, User
from services.channel import mark_post_as_expired, delete_channel_message
from tasks.notifications import send_expiration_notification

logger = logging.getLogger(__name__)

# Глобальный планировщик
scheduler: Optional[AsyncIOScheduler] = None


async def check_expired_posts(bot: Bot):
    """
    Проверяет и деактивирует истёкшие объявления.
    Выполняется каждую минуту.
    """
    logger.debug("Проверка истёкших объявлений...")
    
    try:
        async with get_session() as session:
            # Находим истёкшие активные объявления
            now = datetime.utcnow()
            
            query = select(Post).where(
                Post.status == "active",
                Post.expires_at < now
            )
            
            result = await session.execute(query)
            expired_posts = result.scalars().all()
            
            if expired_posts:
                logger.info(f"Найдено {len(expired_posts)} истёкших объявлений")
                
                for post in expired_posts:
                    try:
                        # Обновляем статус
                        post.status = "expired"
                        
                        # Обновляем сообщение в канале
                        if post.channel_message_id:
                            await mark_post_as_expired(bot, post)
                        
                        # Получаем данные автора
                        author_query = select(User).where(User.id == post.author_id)
                        author_result = await session.execute(author_query)
                        author = author_result.scalar_one_or_none()
                        
                        if author:
                            # Отправляем уведомление автору через Celery
                            send_expiration_notification.delay(
                                user_telegram_id=author.telegram_id,
                                post_data={
                                    "id": post.id,
                                    "from_place": post.from_place,
                                    "to_place": post.to_place,
                                    "role": post.role,
                                    "price": post.price
                                }
                            )
                        
                        logger.info(f"Объявление {post.id} деактивировано")
                        
                    except Exception as e:
                        logger.error(f"Ошибка при деактивации поста {post.id}: {e}")
            
            # Находим объявления, которые истекли более 15 минут назад
            # и удаляем их сообщения из канала
            fifteen_minutes_ago = now - timedelta(minutes=15)
            
            old_expired_query = select(Post).where(
                Post.status == "expired",
                Post.expires_at < fifteen_minutes_ago,
                Post.channel_message_id.isnot(None)  # Только те, что есть в канале
            )
            
            old_expired_result = await session.execute(old_expired_query)
            old_expired_posts = old_expired_result.scalars().all()
            
            if old_expired_posts:
                logger.info(f"Найдено {len(old_expired_posts)} объявлений для удаления из канала (истекли >15 мин назад)")
                
                for post in old_expired_posts:
                    try:
                        if post.channel_message_id:
                            await delete_channel_message(bot, post.channel_message_id)
                            post.channel_message_id = None
                            logger.info(f"Сообщение удалено из канала для поста {post.id}")
                    except Exception as e:
                        logger.warning(f"Не удалось удалить сообщение из канала для поста {post.id}: {e}")
            
            await session.commit()
            
    except Exception as e:
        logger.error(f"Ошибка в check_expired_posts: {e}")


def start_expiration_worker(bot: Bot):
    """
    Запускает фоновый воркер проверки истёкших объявлений.
    
    Args:
        bot: Экземпляр бота
    """
    global scheduler
    
    scheduler = AsyncIOScheduler()
    
    # Добавляем задачу проверки каждую минуту
    scheduler.add_job(
        check_expired_posts,
        trigger=IntervalTrigger(seconds=EXPIRATION_CHECK_INTERVAL),
        args=[bot],
        id="check_expired_posts",
        replace_existing=True,
        max_instances=1
    )
    
    scheduler.start()
    logger.info(f"Воркер истечения запущен (интервал: {EXPIRATION_CHECK_INTERVAL} сек)")


def stop_expiration_worker():
    """Останавливает воркер"""
    global scheduler
    
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Воркер истечения остановлен")


async def extend_post(post_id: int, minutes: int = 60) -> bool:
    """
    Продлевает время жизни объявления.
    
    Args:
        post_id: ID объявления
        minutes: На сколько минут продлить
        
    Returns:
        True при успехе
    """
    try:
        async with get_session() as session:
            query = select(Post).where(Post.id == post_id)
            result = await session.execute(query)
            post = result.scalar_one_or_none()
            
            if not post:
                return False
            
            # Продлеваем от текущего момента
            from datetime import timedelta
            post.expires_at = datetime.utcnow() + timedelta(minutes=minutes)
            post.status = "active"
            
            await session.commit()
            logger.info(f"Объявление {post_id} продлено на {minutes} минут")
            return True
            
    except Exception as e:
        logger.error(f"Ошибка продления объявления {post_id}: {e}")
        return False

