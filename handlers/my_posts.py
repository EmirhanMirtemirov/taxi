# handlers/my_posts.py - Управление своими объявлениями
# Просмотр, приостановка, продление, удаление

from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
import logging

from database.db import get_session
from database.models import User, Post, NotificationLog
from services.channel import delete_channel_message, publish_to_channel
from services.notifications_cleaner import delete_notifications_for_post, delete_notifications_received_by_author
from services.matching import find_matching_subscriptions, get_users_to_notify, find_matching_posts
from tasks.notifications import send_match_notification
from config import POST_LIFETIME_MINUTES, CHANNEL_ID
from keyboards import (
    get_posts_list_keyboard,
    get_post_actions_keyboard,
    get_back_to_menu_keyboard
)

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "my_posts")
async def show_my_posts(callback: CallbackQuery):
    """Показать список объявлений пользователя"""
    await callback.answer()
    
    async with get_session() as session:
        # Получаем пользователя
        user_query = select(User).where(User.telegram_id == callback.from_user.id)
        user_result = await session.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            await callback.message.edit_text("❌ Вы не зарегистрированы. /start")
            return
        
        # Получаем активные и приостановленные объявления
        posts_query = select(Post).where(
            Post.author_id == user.id,
            Post.status.in_(["active", "paused"])
        ).order_by(Post.created_at.desc())
        
        posts_result = await session.execute(posts_query)
        posts = list(posts_result.scalars().all())
        
        if not posts:
            await callback.message.edit_text(
                "📋 <b>Мои объявления</b>\n\n"
                "У вас нет активных объявлений.",
                parse_mode="HTML",
                reply_markup=get_back_to_menu_keyboard()
            )
            return
        
        # Формируем список
        posts_text = []
        for i, post in enumerate(posts, 1):
            status_emoji = "🟢" if post.status == "active" else "⏸"
            
            # Вычисляем оставшееся время
            now = datetime.utcnow()
            remaining = post.expires_at - now
            if remaining.total_seconds() > 0:
                mins = int(remaining.total_seconds() // 60)
                time_text = f"Истекает через {mins} мин"
            else:
                time_text = "Истекло"
            
            posts_text.append(
                f"{i}. {status_emoji} {post.from_place} → {post.to_place}\n"
                f"   ⏰ {time_text}"
            )
        
        await callback.message.edit_text(
            "📋 <b>Ваши объявления:</b>\n\n" +
            "\n\n".join(posts_text),
            parse_mode="HTML",
            reply_markup=get_posts_list_keyboard(posts)
        )


@router.callback_query(F.data.startswith("view_post:"))
async def view_post(callback: CallbackQuery):
    """Просмотр отдельного объявления"""
    await callback.answer()
    
    post_id = int(callback.data.split(":")[1])
    await _display_post(callback, post_id)


async def _display_post(callback: CallbackQuery, post_id: int):
    """Отображение деталей объявления (внутренняя функция)"""
    
    async with get_session() as session:
        query = select(Post).where(Post.id == post_id)
        result = await session.execute(query)
        post = result.scalar_one_or_none()
        
        if not post:
            await callback.answer("Объявление не найдено", show_alert=True)
            return
        
        # Формируем текст
        status_text = "🟢 Активно" if post.status == "active" else "⏸ Приостановлено"
        role_emoji = "🚗" if post.role == "driver" else "🚶"
        seats_line = f"🪑 Мест: {post.seats}\n" if post.seats else ""
        
        # Оставшееся время
        now = datetime.utcnow()
        remaining = post.expires_at - now
        if remaining.total_seconds() > 0:
            mins = int(remaining.total_seconds() // 60)
            time_text = f"через {mins} мин"
        else:
            time_text = "истекло"
        
        text = (
            f"📋 <b>Объявление #{post.id}</b>\n\n"
            f"{role_emoji} Роль: {'Водитель' if post.role == 'driver' else 'Пассажир'}\n\n"
            f"📍 Откуда: {post.from_place}\n"
            f"📍 Куда: {post.to_place}\n"
            f"⏰ Время: {post.departure_time}\n"
            f"{seats_line}"
            f"💰 Цена: {post.price} сом\n\n"
            f"📊 Статус: {status_text}\n"
            f"⏰ Истекает: {time_text}"
        )
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_post_actions_keyboard(post.id, post.status)
        )


@router.callback_query(F.data.startswith("post_action:"))
async def handle_post_action(callback: CallbackQuery, bot: Bot):
    """Обработка действий с объявлением"""
    parts = callback.data.split(":")
    action = parts[1]
    post_id = int(parts[2])
    
    async with get_session() as session:
        query = select(Post).where(Post.id == post_id)
        result = await session.execute(query)
        post = result.scalar_one_or_none()
        
        if not post:
            await callback.answer("Объявление не найдено", show_alert=True)
            return
        
        if action == "pause":
            # Приостановить
            post.status = "paused"
            
            # Удаляем из канала
            if post.channel_message_id:
                await delete_channel_message(bot, post.channel_message_id)
                post.channel_message_id = None
            
            # Удаляем уведомления о совпадениях у подписчиков
            await delete_notifications_for_post(bot, session, post.id)
            
            # Удаляем уведомления, которые получил автор от других объявлений
            await delete_notifications_received_by_author(bot, session, post.author_id)
            
            await session.commit()
            await callback.answer("⏸ Объявление приостановлено")
            
        elif action == "resume":
            # Проверяем нет ли уже активного объявления
            active_check_query = select(Post).where(
                Post.author_id == post.author_id,
                Post.status == "active",
                Post.id != post.id  # Исключаем текущее объявление
            )
            active_check_result = await session.execute(active_check_query)
            existing_active = active_check_result.scalars().first()
            
            if existing_active:
                # Уже есть активное объявление
                await callback.answer(
                    "⚠️ У вас уже есть активное объявление. Сначала приостановите или удалите его.",
                    show_alert=True
                )
                return
            
            # Возобновить
            post.status = "active"
            
            # Получаем автора для публикации
            author_query = select(User).where(User.id == post.author_id)
            author_result = await session.execute(author_query)
            author = author_result.scalar_one()
            
            # Публикуем заново в канал
            msg_id = await publish_to_channel(bot, post, author)
            if msg_id:
                post.channel_message_id = msg_id
            
            await session.commit()
            
            # Ищем совпадения и отправляем уведомления подписчикам
            matching_user_ids = await find_matching_subscriptions(session, post)
            logger.info(f"При возобновлении поста {post.id} найдено {len(matching_user_ids)} совпадений")
            
            if matching_user_ids:
                users_to_notify = await get_users_to_notify(session, post, matching_user_ids)
                logger.info(f"Пользователей для уведомления: {len(users_to_notify)}")
                
                for notify_user in users_to_notify:
                    send_match_notification.delay(
                        recipient_telegram_id=notify_user.telegram_id,
                        post_data={
                            "id": post.id,
                            "role": post.role,
                            "from_place": post.from_place,
                            "to_place": post.to_place,
                            "departure_time": post.departure_time,
                            "seats": post.seats,
                            "price": post.price
                        },
                        author_data={
                            "user_id": author.id,
                            "name": author.phone[:4] + "***",  # Скрываем часть номера
                            "rating": str(author.rating),
                            "car_photo_file_id": author.car_photo_file_id if author.car_photo_file_id else None
                        },
                        recipient_db_id=notify_user.id
                    )
                
                logger.info(f"✅ Запланировано {len(users_to_notify)} уведомлений при возобновлении поста {post.id}")
            
            # Ищем совпадающие объявления противоположной роли
            matching_posts = await find_matching_posts(session, post)
            logger.info(f"При возобновлении поста {post.id} найдено {len(matching_posts)} совпадающих объявлений")
            
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
                        NotificationLog.post_id == post.id,
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
                            "id": post.id,
                            "role": post.role,
                            "from_place": post.from_place,
                            "to_place": post.to_place,
                            "departure_time": post.departure_time,
                            "seats": post.seats,
                            "price": post.price
                        },
                        author_data={
                            "user_id": author.id,
                            "name": author.phone[:4] + "***" if author.phone else "Пользователь",
                            "rating": str(author.rating),
                            "car_photo_file_id": author.car_photo_file_id if author.car_photo_file_id else None
                        },
                        recipient_db_id=matching_author.id
                    )
                    
                    # Также отправляем уведомление автору текущего объявления о совпадающем
                    logger.info(f"Отправляю уведомление автору текущего объявления о совпадающем {matching_post.id}")
                    
                    send_match_notification.delay(
                        recipient_telegram_id=author.telegram_id,
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
                        recipient_db_id=author.id
                    )
                
                logger.info(f"✅ Запланировано отправка уведомлений о совпадающих объявлениях при возобновлении поста {post.id}")
            
            await callback.answer("▶️ Объявление возобновлено")
            
        elif action == "extend":
            # Если объявление приостановлено, проверяем нет ли другого активного
            if post.status == "paused":
                active_check_query = select(Post).where(
                    Post.author_id == post.author_id,
                    Post.status == "active",
                    Post.id != post.id
                )
                active_check_result = await session.execute(active_check_query)
                existing_active = active_check_result.scalars().first()
                
                if existing_active:
                    await callback.answer(
                        "⚠️ У вас уже есть активное объявление. Сначала приостановите или удалите его.",
                        show_alert=True
                    )
                    return
            
            # Продлить на 60 минут
            post.expires_at = datetime.utcnow() + timedelta(minutes=POST_LIFETIME_MINUTES)
            post.status = "active"
            await session.commit()
            await callback.answer(f"🔄 Продлено на {POST_LIFETIME_MINUTES} минут")
            
        elif action == "delete":
            # Удалить
            if post.channel_message_id:
                await delete_channel_message(bot, post.channel_message_id)
            
            # Удаляем уведомления о совпадениях у пользователей
            await delete_notifications_for_post(bot, session, post.id)
            
            # Удаляем уведомления, которые получил автор от других объявлений
            await delete_notifications_received_by_author(bot, session, post.author_id)
            
            post.status = "deleted"
            await session.commit()
            await callback.answer("❌ Объявление удалено")
            
            # Возвращаемся к списку
            await show_my_posts(callback)
            return
    
    # Обновляем отображение
    await _display_post(callback, post_id)

