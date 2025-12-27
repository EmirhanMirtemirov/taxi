# utils/scheduler.py - Планировщик для автоудаления заявок
# Использует APScheduler для периодических задач

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from aiogram import Bot
import logging

from config import CHANNEL_ID, CLEANUP_INTERVAL_MINUTES
from database import get_expired_orders, expire_order
from keyboards import get_expired_order_keyboard

logger = logging.getLogger(__name__)

# Глобальный планировщик
scheduler = AsyncIOScheduler()


async def cleanup_expired_orders(bot: Bot):
    """
    Задача для очистки истёкших заявок.
    Выполняется каждые CLEANUP_INTERVAL_MINUTES минут.
    """
    logger.info("Запуск очистки истёкших заявок...")
    
    try:
        # Получаем все истёкшие заявки
        expired_orders = await get_expired_orders()
        
        for order in expired_orders:
            try:
                # Удаляем сообщение из канала
                if order.get("message_id"):
                    try:
                        await bot.delete_message(CHANNEL_ID, order["message_id"])
                        logger.info(f"Удалено сообщение {order['message_id']} из канала")
                    except Exception as e:
                        logger.warning(f"Не удалось удалить сообщение из канала: {e}")
                
                # Меняем статус заявки
                await expire_order(order["id"])
                
                # Уведомляем пользователя
                try:
                    notification_text = (
                        "⏰ <b>Ваша заявка истекла</b>\n\n"
                        f"📍 {order['point_a']} → {order['point_b']}\n\n"
                        "Никто не откликнулся за 3 часа.\n"
                        "Хотите создать новую?"
                    )
                    
                    await bot.send_message(
                        order["telegram_id"],
                        notification_text,
                        parse_mode="HTML",
                        reply_markup=get_expired_order_keyboard()
                    )
                    logger.info(f"Отправлено уведомление пользователю {order['telegram_id']}")
                    
                except Exception as e:
                    logger.warning(f"Не удалось отправить уведомление: {e}")
                
            except Exception as e:
                logger.error(f"Ошибка при обработке заявки {order['id']}: {e}")
        
        if expired_orders:
            logger.info(f"Обработано {len(expired_orders)} истёкших заявок")
        
    except Exception as e:
        logger.error(f"Ошибка в cleanup_expired_orders: {e}")


def setup_scheduler(bot: Bot):
    """
    Настройка и запуск планировщика.
    
    Args:
        bot: Экземпляр бота для работы с API
    """
    # Добавляем задачу очистки
    scheduler.add_job(
        cleanup_expired_orders,
        trigger=IntervalTrigger(minutes=CLEANUP_INTERVAL_MINUTES),
        args=[bot],
        id="cleanup_expired_orders",
        replace_existing=True
    )
    
    # Запускаем планировщик
    scheduler.start()
    logger.info(f"Планировщик запущен. Очистка каждые {CLEANUP_INTERVAL_MINUTES} минут.")


def shutdown_scheduler():
    """Корректная остановка планировщика"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Планировщик остановлен")

