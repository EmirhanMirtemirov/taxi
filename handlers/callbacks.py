# handlers/callbacks.py - Обработка callback кнопок
# Контакты, пересоздание объявлений и прочие callback

from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
import logging

from database.db import get_session
from database.models import User, Post, NotificationLog, Rating
from services.channel import publish_to_channel
from services.matching import find_matching_subscriptions, get_users_to_notify, log_notification, find_matching_posts
from tasks.notifications import send_match_notification, schedule_rating_request
from config import POST_LIFETIME_MINUTES, RATING_REQUEST_DELAY_HOURS
from utils.helpers import format_local_time, safe_answer_callback
from keyboards import (
    get_contact_keyboard,
    get_back_to_menu_keyboard,
    get_after_publish_keyboard,
    get_existing_post_keyboard
)

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("contact:"))
async def show_contact(callback: CallbackQuery, bot: Bot):
    """
    Показать контакты пользователя.
    ВАЖНО: Работает ТОЛЬКО при совпадении маршрутов!
    """
    logger.info(f"🔔 CALLBACK CONTACT: data='{callback.data}', user={callback.from_user.id}, msg_id={callback.message.message_id if callback.message else None}")
    try:
        await safe_answer_callback(callback, "Обрабатываю...")
        
        parts = callback.data.split(":")
        logger.info(f"Обработка contact callback: {parts}, всего частей: {len(parts)}")
        
        try:
            post_id = int(parts[1])
            author_user_id = int(parts[2])  # Это ID в нашей БД, не telegram_id
        except (IndexError, ValueError) as e:
            logger.error(f"Ошибка парсинга callback data: {e}, parts: {parts}")
            await safe_answer_callback(callback, "Ошибка данных", show_alert=True)
            return
        
        async with get_session() as session:
            # Получаем объявление
            post_query = select(Post).where(Post.id == post_id)
            post_result = await session.execute(post_query)
            post = post_result.scalar_one_or_none()
            
            if not post:
                await callback.message.edit_text(
                    "❌ Объявление не найдено или удалено.",
                    reply_markup=get_back_to_menu_keyboard()
                )
                return
            
            # Получаем автора объявления
            author_query = select(User).where(User.id == author_user_id)
            author_result = await session.execute(author_query)
            author = author_result.scalar_one_or_none()
            
            if not author:
                await callback.message.edit_text(
                    "❌ Пользователь не найден.",
                    reply_markup=get_back_to_menu_keyboard()
                )
                return
            
            # Получаем информацию о пользователе из Telegram для имени
            try:
                author_chat = await bot.get_chat(author.telegram_id)
                author_name = author_chat.first_name or author_chat.username or "Пользователь"
            except Exception as e:
                logger.warning(f"Не удалось получить имя автора из Telegram: {e}")
                author_name = author.username or "Пользователь"
            
            # Формируем контактную информацию
            role_text = "Водитель" if author.role == "driver" else "Пассажир"
            rating_text = f"{float(author.rating):.1f}"
            rating_count = f"({author.rating_count} оценок)" if author.rating_count > 0 else ""
            
            text = (
                "📞 <b>Контактные данные:</b>\n\n"
                f"🎭 Роль: {role_text}\n"
                f"👤 Имя: {author_name}\n"
                f"📱 Телефон: {author.phone}\n"
                f"⭐ Рейтинг: {rating_text} {rating_count}\n\n"
                f"📍 Маршрут:\n"
                f"{post.from_place} → {post.to_place}\n"
                f"💰 Цена: {post.price} сом"
            )
            
            await callback.message.edit_text(
                text,
                parse_mode="HTML",
                reply_markup=get_contact_keyboard(author.phone, author.telegram_id)
            )
            
            logger.info(f"Контакты показаны для поста {post_id}, автор: {author_user_id}")
            
            # Планируем запрос на рейтинг через 2 часа
            # Получаем текущего пользователя
            current_user_query = select(User).where(User.telegram_id == callback.from_user.id)
            current_user_result = await session.execute(current_user_query)
            current_user = current_user_result.scalar_one_or_none()
            
            if current_user:
                # Проверяем, не поставлены ли уже оценки
                # Проверяем, не оценил ли уже текущий пользователь автора
                rating_check_1 = select(Rating).where(
                    Rating.from_user_id == current_user.id,
                    Rating.to_user_id == author.id,
                    Rating.post_id == post_id
                )
                rating_result_1 = await session.execute(rating_check_1)
                existing_rating_1 = rating_result_1.scalar_one_or_none()
                
                # Проверяем, не оценил ли уже автор текущего пользователя
                rating_check_2 = select(Rating).where(
                    Rating.from_user_id == author.id,
                    Rating.to_user_id == current_user.id,
                    Rating.post_id == post_id
                )
                rating_result_2 = await session.execute(rating_check_2)
                existing_rating_2 = rating_result_2.scalar_one_or_none()
                
                # Планируем оценку от текущего пользователя автору (если еще не оценено)
                if not existing_rating_1:
                    schedule_rating_request.apply_async(
                        args=[
                            callback.from_user.id,  # Кто оценивает
                            author.telegram_id,      # Кого оценивают
                            "пользователя",          # Имя (упрощённо)
                            post_id,
                            post.from_place,
                            post.to_place
                        ],
                        countdown=RATING_REQUEST_DELAY_HOURS * 3600  # Через 2 часа
                    )
                    logger.info(f"Запланирован запрос на рейтинг: {callback.from_user.id} → {author.telegram_id} для поста {post_id}")
                else:
                    logger.info(f"Оценка уже поставлена: {callback.from_user.id} → {author.telegram_id} для поста {post_id}, пропускаем запрос")
                
                # И наоборот - от автора текущему пользователю (если еще не оценено)
                if not existing_rating_2:
                    schedule_rating_request.apply_async(
                        args=[
                            author.telegram_id,
                            callback.from_user.id,
                            "пользователя",
                            post_id,
                            post.from_place,
                            post.to_place
                        ],
                        countdown=RATING_REQUEST_DELAY_HOURS * 3600
                    )
                    logger.info(f"Запланирован запрос на рейтинг: {author.telegram_id} → {callback.from_user.id} для поста {post_id}")
                else:
                    logger.info(f"Оценка уже поставлена: {author.telegram_id} → {callback.from_user.id} для поста {post_id}, пропускаем запрос")
        
    except Exception as e:
        logger.error(f"Ошибка в show_contact: {e}", exc_info=True)
        await safe_answer_callback(callback, "Произошла ошибка", show_alert=True)


@router.callback_query(F.data.startswith("recreate:"))
async def recreate_post(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Пересоздать объявление с теми же данными"""
    await safe_answer_callback(callback, "Создаю...")
    
    try:
        post_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await safe_answer_callback(callback, "Ошибка данных", show_alert=True)
        return
    
    async with get_session() as session:
        # Получаем старое объявление
        old_post_query = select(Post).where(Post.id == post_id)
        old_post_result = await session.execute(old_post_query)
        old_post = old_post_result.scalar_one_or_none()
        
        if not old_post:
            await callback.message.edit_text(
                "❌ Объявление не найдено.",
                reply_markup=get_back_to_menu_keyboard()
            )
            return
        
        # Получаем пользователя
        user_query = select(User).where(User.telegram_id == callback.from_user.id)
        user_result = await session.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            await callback.message.edit_text(
                "❌ Вы не зарегистрированы. /start"
            )
            return
        
        # Проверяем наличие АКТИВНОГО объявления (приостановленные не блокируют)
        active_post_query = select(Post).where(
            Post.author_id == user.id,
            Post.status == "active"
        )
        active_post_result = await session.execute(active_post_query)
        active_post = active_post_result.scalars().first()
        
        if active_post:
            # У пользователя уже есть активное объявление
            await callback.message.edit_text(
                f"⚠️ <b>У вас уже есть активное объявление</b>\n\n"
                f"📍 {active_post.from_place} → {active_post.to_place}\n"
                f"🕐 {active_post.departure_time}\n"
                f"Статус: 🟢 активно\n\n"
                f"Чтобы создать новое объявление, сначала удалите или приостановите текущее.",
                parse_mode="HTML",
                reply_markup=get_existing_post_keyboard(active_post.id, active_post.status)
            )
            return
        
        # Создаём новое объявление
        expires_at = datetime.utcnow() + timedelta(minutes=POST_LIFETIME_MINUTES)
        
        new_post = Post(
            author_id=user.id,
            role=old_post.role,
            from_place=old_post.from_place,
            to_place=old_post.to_place,
            keys_from=old_post.keys_from,
            keys_to=old_post.keys_to,
            departure_time="сейчас",  # Обновляем время
            seats=old_post.seats,
            price=old_post.price,
            expires_at=expires_at
        )
        
        session.add(new_post)
        await session.flush()
        
        # Публикуем в канал
        msg_id = await publish_to_channel(bot, new_post, user)
        if msg_id:
            new_post.channel_message_id = msg_id
        
        await session.commit()
        
        # Ищем совпадения
        matching_user_ids = await find_matching_subscriptions(session, new_post)
        
        if matching_user_ids:
            users_to_notify = await get_users_to_notify(session, new_post, matching_user_ids)
            
            for notify_user in users_to_notify:
                send_match_notification.delay(
                    recipient_telegram_id=notify_user.telegram_id,
                    post_data={
                        "id": new_post.id,
                        "role": new_post.role,
                        "from_place": new_post.from_place,
                        "to_place": new_post.to_place,
                        "departure_time": new_post.departure_time,
                        "seats": new_post.seats,
                        "price": new_post.price
                    },
                    author_data={
                        "user_id": user.id,
                        "name": callback.from_user.first_name,
                        "rating": str(user.rating),
                        "car_photo_file_id": user.car_photo_file_id if user.car_photo_file_id else None
                    },
                    recipient_db_id=notify_user.id
                )
        
        # Ищем совпадающие объявления противоположной роли
        matching_posts = await find_matching_posts(session, new_post)
        logger.info(f"При пересоздании поста {new_post.id} найдено {len(matching_posts)} совпадающих объявлений")
        
        if matching_posts:
            # Получаем авторов совпадающих объявлений
            matching_author_ids = [p.author_id for p in matching_posts]
            authors_query = select(User).where(User.id.in_(matching_author_ids))
            authors_result = await session.execute(authors_query)
            matching_authors = {author.id: author for author in authors_result.scalars().all()}
            
            # Отправляем уведомления авторам совпадающих объявлений
            for matching_post in matching_posts:
                matching_author = matching_authors.get(matching_post.author_id)
                if not matching_author:
                    continue
                
                # Проверяем, не отправляли ли уже уведомление этому пользователю
                already_notified_query = select(NotificationLog).where(
                    NotificationLog.post_id == new_post.id,
                    NotificationLog.recipient_id == matching_author.id
                )
                already_result = await session.execute(already_notified_query)
                if already_result.scalar_one_or_none():
                    logger.info(f"Пропускаем {matching_author.id} - уже получил уведомление")
                    continue
                
                logger.info(f"Отправляю уведомление автору совпадающего объявления {matching_post.id} (user_id={matching_author.id})")
                
                send_match_notification.delay(
                    recipient_telegram_id=matching_author.telegram_id,
                    post_data={
                        "id": new_post.id,
                        "role": new_post.role,
                        "from_place": new_post.from_place,
                        "to_place": new_post.to_place,
                        "departure_time": new_post.departure_time,
                        "seats": new_post.seats,
                        "price": new_post.price
                    },
                    author_data={
                        "user_id": user.id,
                        "name": callback.from_user.first_name,
                        "rating": str(user.rating),
                        "car_photo_file_id": user.car_photo_file_id if user.car_photo_file_id else None
                    },
                    recipient_db_id=matching_author.id
                )
                
                # Также отправляем уведомление автору текущего объявления о совпадающем
                logger.info(f"Отправляю уведомление автору текущего объявления о совпадающем {matching_post.id}")
                
                send_match_notification.delay(
                    recipient_telegram_id=user.telegram_id,
                    post_data={
                        "id": matching_post.id,
                        "role": matching_post.role,
                        "from_place": matching_post.from_place,
                        "to_place": matching_post.to_place,
                        "departure_time": matching_post.departure_time,
                        "seats": matching_post.seats,
                        "price": matching_post.price
                    },
                    author_data={
                        "user_id": matching_author.id,
                        "name": matching_author.phone[:4] + "***" if matching_author.phone else "Пользователь",
                        "rating": str(matching_author.rating),
                        "car_photo_file_id": matching_author.car_photo_file_id if matching_author.car_photo_file_id else None
                    },
                    recipient_db_id=user.id
                )
            
            logger.info(f"✅ Запланировано отправка уведомлений о совпадающих объявлениях при пересоздании поста {new_post.id}")
        
        logger.info(f"Объявление {new_post.id} пересоздано из {post_id}")
    
    expires_time = format_local_time(expires_at)
    
    await callback.message.edit_text(
        f"✅ <b>Объявление опубликовано!</b>\n\n"
        f"⏰ Активно {POST_LIFETIME_MINUTES} минут (до {expires_time})\n\n"
        "Управление объявлением:",
        parse_mode="HTML",
        reply_markup=get_after_publish_keyboard()
    )


@router.callback_query(F.data == "post:pause")
async def pause_current_post(callback: CallbackQuery, bot: Bot):
    """Приостановить текущее объявление (из сообщения после публикации)"""
    await safe_answer_callback(callback)
    
    # Находим последнее активное объявление пользователя
    async with get_session() as session:
        user_query = select(User).where(User.telegram_id == callback.from_user.id)
        user_result = await session.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            return
        
        post_query = select(Post).where(
            Post.author_id == user.id,
            Post.status == "active"
        ).order_by(Post.created_at.desc()).limit(1)
        
        post_result = await session.execute(post_query)
        post = post_result.scalar_one_or_none()
        
        if not post:
            await safe_answer_callback(callback, "Нет активных объявлений", show_alert=True)
            return
        
        from services.channel import delete_channel_message
        from services.notifications_cleaner import delete_notifications_for_post, delete_notifications_received_by_author
        
        post.status = "paused"
        if post.channel_message_id:
            await delete_channel_message(bot, post.channel_message_id)
            post.channel_message_id = None
        
        # Удаляем уведомления о совпадениях у подписчиков
        await delete_notifications_for_post(bot, session, post.id)
        
        # Удаляем уведомления, которые получил автор от других объявлений
        await delete_notifications_received_by_author(bot, session, post.author_id)
        
        await session.commit()
    
    await callback.message.edit_text(
        "⏸ <b>Объявление приостановлено</b>\n\n"
        "Вы можете возобновить его в разделе «Мои объявления».",
        parse_mode="HTML",
        reply_markup=get_back_to_menu_keyboard()
    )


@router.callback_query(F.data == "post:delete")
async def delete_current_post(callback: CallbackQuery, bot: Bot):
    """Удалить текущее объявление"""
    await safe_answer_callback(callback)
    
    async with get_session() as session:
        user_query = select(User).where(User.telegram_id == callback.from_user.id)
        user_result = await session.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            return
        
        post_query = select(Post).where(
            Post.author_id == user.id,
            Post.status.in_(["active", "paused"])
        ).order_by(Post.created_at.desc()).limit(1)
        
        post_result = await session.execute(post_query)
        post = post_result.scalar_one_or_none()
        
        if not post:
            await safe_answer_callback(callback, "Нет объявлений для удаления", show_alert=True)
            return
        
        from services.channel import delete_channel_message
        from services.notifications_cleaner import delete_notifications_for_post
        
        # Удаляем сообщение из канала
        if post.channel_message_id:
            await delete_channel_message(bot, post.channel_message_id)
        
        # Удаляем уведомления о совпадениях у пользователей
        await delete_notifications_for_post(bot, session, post.id)
        
        post.status = "deleted"
        await session.commit()
    
    await callback.message.edit_text(
        "❌ <b>Объявление удалено</b>",
        parse_mode="HTML",
        reply_markup=get_back_to_menu_keyboard()
    )

