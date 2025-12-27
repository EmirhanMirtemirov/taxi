# tasks/notifications.py - Celery задачи для уведомлений
# Асинхронная отправка уведомлений через очередь

import asyncio
import logging
from typing import Dict, Any

from celery_app import celery
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import BOT_TOKEN, DATABASE_URL

logger = logging.getLogger(__name__)


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def send_match_notification(
    self,
    recipient_telegram_id: int,
    post_data: Dict[str, Any],
    author_data: Dict[str, Any],
    recipient_db_id: int = None
):
    """
    Отправляет уведомление о совпадении маршрута.
    Выполняется асинхронно через Celery.
    
    Args:
        recipient_telegram_id: Telegram ID получателя
        post_data: Данные объявления (dict)
        author_data: Данные автора объявления (dict)
        recipient_db_id: ID получателя в БД (для сохранения в лог)
    """
    async def send():
        bot = Bot(token=BOT_TOKEN)
        
        try:
            # Определяем тип объявления
            role_emoji = "🚗" if post_data["role"] == "driver" else "🚶"
            role_text = "Водитель" if post_data["role"] == "driver" else "Пассажир"
            
            # Дополнительная строка для водителя
            seats_line = f"🪑 Мест: {post_data.get('seats', '—')}\n" if post_data["role"] == "driver" else ""
            
            text = (
                f"🔔 <b>Найден попутчик!</b>\n\n"
                f"{role_emoji} {role_text} едет по вашему маршруту:\n\n"
                f"📍 <b>Откуда:</b> {post_data['from_place']}\n"
                f"📍 <b>Куда:</b> {post_data['to_place']}\n"
                f"⏰ <b>Время:</b> {post_data.get('departure_time', 'Не указано')}\n"
                f"{seats_line}"
                f"💰 <b>Цена:</b> {post_data['price']} сом\n"
                f"⭐ <b>Рейтинг:</b> {author_data['rating']}\n"
            )
            
            # Кнопка "Связаться" показывается ТОЛЬКО при совпадении
            callback_data_value = f"contact:{post_data['id']}:{author_data['user_id']}"
            logger.info(f"Формирую callback_data для кнопки: '{callback_data_value}' (длина: {len(callback_data_value)})")
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="📞 Связаться",
                    callback_data=callback_data_value
                )],
                [InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="main_menu"
                )]
            ])
            
            # Если это водитель и у него есть фото автомобиля - отправляем фото
            car_photo_file_id = author_data.get("car_photo_file_id")
            if post_data["role"] == "driver" and car_photo_file_id:
                message = await bot.send_photo(
                    chat_id=recipient_telegram_id,
                    photo=car_photo_file_id,
                    caption=text,
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                # Обычное текстовое сообщение
                message = await bot.send_message(
                chat_id=recipient_telegram_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
            logger.info(f"✅ Уведомление отправлено пользователю {recipient_telegram_id} (msg_id={message.message_id}) с callback_data: {callback_data_value}")
            
            # Сохраняем message_id в БД (не критично, если не получится)
            if recipient_db_id:
                try:
                    # Создаем НОВЫЙ engine и session специально для этой задачи
                    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
                    from database.models import NotificationLog
                    from config import DATABASE_URL
                    
                    # Создаём изолированный engine для этой задачи
                    task_engine = create_async_engine(DATABASE_URL, echo=False)
                    task_session_maker = async_sessionmaker(task_engine, class_=AsyncSession, expire_on_commit=False)
                    
                    async with task_session_maker() as task_session:
                        log_entry = NotificationLog(
                            post_id=post_data['id'],
                            recipient_id=recipient_db_id,
                            notification_message_id=message.message_id,
                            recipient_telegram_id=recipient_telegram_id
                        )
                        task_session.add(log_entry)
                        await task_session.commit()
                        logger.info(f"✅ Сохранено в лог: post_id={post_data['id']}, recipient_id={recipient_db_id}, msg_id={message.message_id}")
                    
                    # Закрываем engine
                    await task_engine.dispose()
                except Exception as db_error:
                    # Не прерываем выполнение, если не удалось сохранить в БД
                    logger.warning(f"⚠️ Не удалось сохранить уведомление в БД: {db_error}. Уведомление отправлено, но не будет удалено при удалении поста.")
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
            raise
        finally:
            await bot.session.close()
    
    try:
        asyncio.run(send())
    except Exception as exc:
        logger.error(f"Celery task failed: {exc}")
        raise self.retry(exc=exc)


@celery.task(bind=True, max_retries=3, default_retry_delay=60)
def schedule_rating_request(
    self,
    from_user_telegram_id: int,
    to_user_telegram_id: int,
    to_user_name: str,
    post_id: int,
    from_place: str,
    to_place: str
):
    """
    Отправляет запрос на оценку поездки.
    Вызывается через 2 часа после совпадения.
    
    Args:
        from_user_telegram_id: Кто оценивает
        to_user_telegram_id: Кого оценивают  
        to_user_name: Имя оцениваемого
        post_id: ID объявления
        from_place: Откуда
        to_place: Куда
    """
    async def send():
        bot = Bot(token=BOT_TOKEN)
        
        try:
            # Проверяем, не поставлена ли уже оценка
            from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
            from sqlalchemy import select
            from database.models import User, Rating
            
            task_engine = create_async_engine(DATABASE_URL, echo=False)
            task_session_maker = async_sessionmaker(task_engine, class_=AsyncSession, expire_on_commit=False)
            
            async with task_session_maker() as session:
                # Получаем пользователей по telegram_id
                from_user_query = select(User).where(User.telegram_id == from_user_telegram_id)
                from_user_result = await session.execute(from_user_query)
                from_user = from_user_result.scalar_one_or_none()
                
                to_user_query = select(User).where(User.telegram_id == to_user_telegram_id)
                to_user_result = await session.execute(to_user_query)
                to_user = to_user_result.scalar_one_or_none()
                
                if not from_user or not to_user:
                    logger.warning(f"Пользователи не найдены для запроса на рейтинг: from={from_user_telegram_id}, to={to_user_telegram_id}")
                    return
                
                # Проверяем, не поставлена ли уже оценка
                existing_rating_query = select(Rating).where(
                    Rating.from_user_id == from_user.id,
                    Rating.to_user_id == to_user.id,
                    Rating.post_id == post_id
                )
                existing_rating_result = await session.execute(existing_rating_query)
                existing_rating = existing_rating_result.scalar_one_or_none()
                
                if existing_rating:
                    logger.info(f"Оценка уже поставлена пользователем {from_user_telegram_id} для поста {post_id}, пропускаем запрос")
                    return
                
                # Отправляем запрос на оценку
            text = (
                f"⭐ <b>Оцените поездку</b>\n\n"
                f"Как прошла поездка с {to_user_name}?\n"
                f"📍 Маршрут: {from_place} → {to_place}\n"
            )
            
            # Кнопки оценки
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="⭐ 1", callback_data=f"rate:{post_id}:{to_user_telegram_id}:1"),
                    InlineKeyboardButton(text="⭐ 2", callback_data=f"rate:{post_id}:{to_user_telegram_id}:2"),
                    InlineKeyboardButton(text="⭐ 3", callback_data=f"rate:{post_id}:{to_user_telegram_id}:3"),
                    InlineKeyboardButton(text="⭐ 4", callback_data=f"rate:{post_id}:{to_user_telegram_id}:4"),
                    InlineKeyboardButton(text="⭐ 5", callback_data=f"rate:{post_id}:{to_user_telegram_id}:5"),
                ],
                    [InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"rate:skip:{post_id}:{to_user_telegram_id}")]
            ])
            
            await bot.send_message(
                chat_id=from_user_telegram_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
            logger.info(f"Запрос на рейтинг отправлен пользователю {from_user_telegram_id} для поста {post_id}")
            
            await task_engine.dispose()
            
        except Exception as e:
            logger.error(f"Ошибка отправки запроса на рейтинг: {e}")
            raise
        finally:
            await bot.session.close()
    
    try:
        asyncio.run(send())
    except Exception as exc:
        logger.error(f"Rating request task failed: {exc}")
        raise self.retry(exc=exc)


@celery.task(bind=True, max_retries=3)
def send_expiration_notification(
    self,
    user_telegram_id: int,
    post_data: Dict[str, Any]
):
    """
    Отправляет уведомление об истечении объявления.
    
    Args:
        user_telegram_id: Telegram ID автора
        post_data: Данные объявления
    """
    async def send():
        bot = Bot(token=BOT_TOKEN)
        
        try:
            text = (
                f"⏰ <b>Ваше объявление истекло</b>\n\n"
                f"📍 {post_data['from_place']} → {post_data['to_place']}\n\n"
                f"Хотите создать новое?"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🔄 Создать такое же",
                    callback_data=f"recreate:{post_data['id']}"
                )],
                [InlineKeyboardButton(
                    text="📝 Новое объявление",
                    callback_data="create_post"
                )],
                [InlineKeyboardButton(
                    text="🏠 В меню",
                    callback_data="main_menu"
                )]
            ])
            
            await bot.send_message(
                chat_id=user_telegram_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard
            )
            
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об истечении: {e}")
        finally:
            await bot.session.close()
    
    asyncio.run(send())

