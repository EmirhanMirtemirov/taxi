# services/notifications_cleaner.py - Удаление уведомлений при удалении объявления
# Удаляет уведомления о совпадениях у пользователей, когда объявление удаляется

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram import Bot
import logging

from database.models import NotificationLog

logger = logging.getLogger(__name__)


async def delete_notifications_for_post(
    bot: Bot,
    session: AsyncSession,
    post_id: int
) -> int:
    """
    Удаляет все уведомления о совпадениях для указанного объявления.
    
    Args:
        bot: Экземпляр бота
        session: Сессия БД
        post_id: ID объявления
        
    Returns:
        Количество удаленных уведомлений
    """
    logger.info(f"🔍 Начинаю удаление уведомлений для поста {post_id}")
    
    # Получаем все уведомления для этого поста
    query = select(NotificationLog).where(
        NotificationLog.post_id == post_id
    )
    result = await session.execute(query)
    notifications = result.scalars().all()
    
    logger.info(f"📋 Найдено {len(notifications)} записей в логе для поста {post_id}")
    
    deleted_count = 0
    
    for notification in notifications:
        logger.info(f"   - Запись: msg_id={notification.notification_message_id}, tg_id={notification.recipient_telegram_id}")
        
        if notification.notification_message_id and notification.recipient_telegram_id:
            try:
                await bot.delete_message(
                    chat_id=notification.recipient_telegram_id,
                    message_id=notification.notification_message_id
                )
                deleted_count += 1
                logger.info(
                    f"✅ Удалено сообщение {notification.notification_message_id} "
                    f"у пользователя {notification.recipient_telegram_id}"
                )
            except Exception as e:
                # Сообщение уже удалено или недоступно
                logger.warning(
                    f"⚠️ Не удалось удалить сообщение {notification.notification_message_id} "
                    f"у пользователя {notification.recipient_telegram_id}: {e}"
                )
        else:
            logger.warning(f"   ⚠️ Пропуск: нет msg_id или tg_id")
    
    # Удаляем записи из лога (commit будет сделан вызывающим кодом)
    if notifications:
        for notification in notifications:
            await session.delete(notification)
        logger.info(f"🗑 Помечено к удалению {len(notifications)} записей из БД, удалено {deleted_count} сообщений из чатов для поста {post_id}")
    else:
        logger.info(f"ℹ️ Нет записей для удаления для поста {post_id}")
    
    return deleted_count


async def delete_notifications_received_by_author(
    bot: Bot,
    session: AsyncSession,
    author_id: int
) -> int:
    """
    Удаляет все уведомления, которые получил автор объявления от других объявлений.
    Используется когда автор удаляет/приостанавливает своё объявление.
    
    Args:
        bot: Экземпляр бота
        session: Сессия БД
        author_id: ID автора объявления
        
    Returns:
        Количество удаленных уведомлений
    """
    logger.info(f"🔍 Начинаю удаление уведомлений, полученных автором {author_id}")
    
    # Получаем все уведомления, которые получил этот автор
    query = select(NotificationLog).where(
        NotificationLog.recipient_id == author_id
    )
    result = await session.execute(query)
    notifications = result.scalars().all()
    
    logger.info(f"📋 Найдено {len(notifications)} уведомлений, полученных автором {author_id}")
    
    deleted_count = 0
    
    for notification in notifications:
        logger.info(f"   - Запись: msg_id={notification.notification_message_id}, tg_id={notification.recipient_telegram_id}")
        
        if notification.notification_message_id and notification.recipient_telegram_id:
            try:
                await bot.delete_message(
                    chat_id=notification.recipient_telegram_id,
                    message_id=notification.notification_message_id
                )
                deleted_count += 1
                logger.info(
                    f"✅ Удалено сообщение {notification.notification_message_id} "
                    f"у пользователя {notification.recipient_telegram_id}"
                )
            except Exception as e:
                logger.warning(
                    f"⚠️ Не удалось удалить сообщение {notification.notification_message_id} "
                    f"у пользователя {notification.recipient_telegram_id}: {e}"
                )
        else:
            logger.warning(f"   ⚠️ Пропуск: нет msg_id или tg_id")
    
    # Удаляем записи из лога (commit будет сделан вызывающим кодом)
    if notifications:
        for notification in notifications:
            await session.delete(notification)
        logger.info(f"🗑 Помечено к удалению {len(notifications)} записей из БД, удалено {deleted_count} сообщений из чатов для автора {author_id}")
    else:
        logger.info(f"ℹ️ Нет уведомлений для удаления для автора {author_id}")
    
    return deleted_count

