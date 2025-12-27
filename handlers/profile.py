# handlers/profile.py - Профиль пользователя
# Просмотр и редактирование профиля, смена роли

from datetime import datetime
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
import re
import logging

from states import EditProfile
from database.db import get_session
from database.models import User, Post, Subscription, NotificationLog, Rating, RatingRequest
from services.channel import delete_channel_message
from services.notifications_cleaner import delete_notifications_for_post, delete_notifications_received_by_author
from utils.message_cleaner import add_message_to_delete, clean_chat
from keyboards import (
    get_profile_keyboard,
    get_role_change_keyboard,
    get_phone_keyboard,
    get_remove_keyboard,
    get_back_to_menu_keyboard,
    get_delete_profile_confirm_keyboard
)

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery, state: FSMContext):
    """Показать профиль"""
    await callback.answer()
    await state.clear()
    
    async with get_session() as session:
        query = select(User).where(User.telegram_id == callback.from_user.id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.message.edit_text("❌ Вы не зарегистрированы. /start")
            return
        
        role_text = "🚗 Водитель" if user.role == "driver" else "🚶 Пассажир"
        rating_text = f"{float(user.rating):.1f}"
        rating_count = f"({user.rating_count} оценок)" if user.rating_count > 0 else "(нет оценок)"
        created_date = user.created_at.strftime("%d.%m.%Y")
        
        # Формируем текст профиля
        text = (
            "👤 <b>Ваш профиль</b>\n\n"
            f"📛 Имя: {callback.from_user.first_name}\n"
            f"📱 Телефон: {user.phone}\n"
            f"🎭 Роль: {role_text}\n"
        )
        
        # Для водителей добавляем информацию об автомобиле
        if user.role == "driver":
            if user.car_number:
                text += f"🚗 Номер авто: {user.car_number}\n"
            else:
                text += "🚗 Номер авто: не указан\n"
        
        text += (
            f"⭐ Рейтинг: {rating_text} {rating_count}\n"
            f"📅 В системе с: {created_date}"
        )
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_profile_keyboard()
        )


@router.callback_query(F.data == "profile:phone")
async def start_edit_phone(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Начало редактирования телефона"""
    await callback.answer()
    
    # Очищаем предыдущие сообщения перед началом редактирования
    await clean_chat(bot, callback.from_user.id, state)
    await state.update_data(messages_to_delete=[])
    
    try:
        await callback.message.delete()
    except:
        pass
    
    msg = await callback.message.answer(
        "📱 <b>Изменение телефона</b>\n\n"
        "Отправьте новый номер телефона:\n"
        "<i>Формат: +996XXXXXXXXX</i>",
        parse_mode="HTML",
        reply_markup=get_phone_keyboard()
    )
    await add_message_to_delete(state, msg.message_id)
    
    await state.set_state(EditProfile.editing_phone)


@router.message(EditProfile.editing_phone)
async def process_new_phone(message: Message, state: FSMContext, bot: Bot):
    """Обработка нового телефона"""
    if message.text == "❌ Отмена":
        await clean_chat(bot, message.chat.id, state)
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_remove_keyboard())
        await message.answer("Что дальше?", reply_markup=get_back_to_menu_keyboard())
        return
    
    # Обрабатываем контакт или текст
    phone = None
    
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    elif message.text:
        phone = message.text.replace(" ", "").replace("-", "")
        if phone.startswith("0"):
            phone = "+996" + phone[1:]
        if not phone.startswith("+"):
            phone = "+" + phone
    
    # Валидация
    pattern = r'^\+996\d{9}$'
    if not phone or not re.match(pattern, phone):
        await add_message_to_delete(state, message.message_id)
        msg = await message.answer(
            "❌ Неверный формат. Используйте: +996XXXXXXXXX",
            reply_markup=get_phone_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        return
    
    # Добавляем сообщение пользователя в список для удаления
    await add_message_to_delete(state, message.message_id)
    
    # Обновляем в БД
    async with get_session() as session:
        query = select(User).where(User.telegram_id == message.from_user.id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        
        if user:
            user.phone = phone
            await session.commit()
    
    # Очищаем все временные сообщения перед завершением редактирования
    await clean_chat(bot, message.chat.id, state)
    await state.clear()
    
    await message.answer(
        "✅ Телефон успешно изменён!",
        reply_markup=get_remove_keyboard()
    )
    
    await message.answer(
        "Что дальше?",
        reply_markup=get_back_to_menu_keyboard()
    )


@router.callback_query(F.data == "profile:role")
async def show_role_change(callback: CallbackQuery):
    """Показать опции смены роли"""
    await callback.answer()
    
    async with get_session() as session:
        query = select(User).where(User.telegram_id == callback.from_user.id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            return
        
        current_role = "Водитель" if user.role == "driver" else "Пассажир"
        
        await callback.message.edit_text(
            f"🔄 <b>Смена роли</b>\n\n"
            f"Текущая роль: <b>{current_role}</b>\n\n"
            "Выберите новую роль:",
            parse_mode="HTML",
            reply_markup=get_role_change_keyboard(user.role)
        )


@router.callback_query(F.data.startswith("switch_role:"))
async def switch_role(callback: CallbackQuery):
    """Смена роли"""
    new_role = callback.data.split(":")[1]
    
    async with get_session() as session:
        query = select(User).where(User.telegram_id == callback.from_user.id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            return
        
        if user.role == new_role:
            await callback.answer("Вы уже в этой роли!", show_alert=True)
            return
        
        user.role = new_role
        await session.commit()
    
    role_text = "🚗 Водитель" if new_role == "driver" else "🚶 Пассажир"
    
    await callback.answer(f"✅ Роль изменена на: {role_text}")
    
    await callback.message.edit_text(
        f"✅ <b>Роль изменена!</b>\n\n"
        f"Новая роль: {role_text}",
        parse_mode="HTML",
        reply_markup=get_back_to_menu_keyboard()
    )


@router.callback_query(F.data == "profile:delete")
async def show_delete_confirm(callback: CallbackQuery):
    """Показать подтверждение удаления профиля"""
    await callback.answer()
    
    await callback.message.edit_text(
        "⚠️ <b>Удаление профиля</b>\n\n"
        "Вы уверены, что хотите удалить свой профиль?\n\n"
        "Это действие удалит:\n"
        "• Все ваши объявления\n"
        "• Все ваши подписки\n"
        "• Историю уведомлений\n"
        "• Данные профиля\n\n"
        "❌ <b>Это действие необратимо!</b>",
        parse_mode="HTML",
        reply_markup=get_delete_profile_confirm_keyboard()
    )


@router.callback_query(F.data == "profile:delete_confirm")
async def delete_profile(callback: CallbackQuery, bot: Bot):
    """Удаление профиля пользователя"""
    await callback.answer("Удаляю профиль...")
    
    async with get_session() as session:
        # Получаем пользователя
        query = select(User).where(User.telegram_id == callback.from_user.id)
        result = await session.execute(query)
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.message.edit_text(
                "❌ Пользователь не найден",
                reply_markup=get_back_to_menu_keyboard()
            )
            return
        
        # Удаляем все объявления пользователя
        posts_query = select(Post).where(Post.author_id == user.id)
        posts_result = await session.execute(posts_query)
        posts = posts_result.scalars().all()
        
        for post in posts:
            # Удаляем сообщения из канала
            if post.channel_message_id:
                try:
                    await delete_channel_message(bot, post.channel_message_id)
                except:
                    pass
            
            # Удаляем уведомления о совпадениях
            try:
                await delete_notifications_for_post(bot, session, post.id)
            except:
                pass
        
        # Удаляем уведомления, которые получил пользователь
        try:
            await delete_notifications_received_by_author(bot, session, user.id)
        except:
            pass
        
        # Удаляем все подписки пользователя
        subscriptions_query = select(Subscription).where(Subscription.user_id == user.id)
        subscriptions_result = await session.execute(subscriptions_query)
        subscriptions = subscriptions_result.scalars().all()
        for sub in subscriptions:
            await session.delete(sub)
        
        # Удаляем все записи в логе уведомлений, где пользователь был получателем
        notifications_query = select(NotificationLog).where(NotificationLog.recipient_id == user.id)
        notifications_result = await session.execute(notifications_query)
        notifications = notifications_result.scalars().all()
        for notification in notifications:
            await session.delete(notification)
        
        # Удаляем все оценки, где пользователь был оценщиком или получателем
        ratings_from_query = select(Rating).where(Rating.from_user_id == user.id)
        ratings_from_result = await session.execute(ratings_from_query)
        ratings_from = ratings_from_result.scalars().all()
        for rating in ratings_from:
            await session.delete(rating)
        
        ratings_to_query = select(Rating).where(Rating.to_user_id == user.id)
        ratings_to_result = await session.execute(ratings_to_query)
        ratings_to = ratings_to_result.scalars().all()
        for rating in ratings_to:
            await session.delete(rating)
        
        # Удаляем все запросы на оценку, где пользователь участвовал
        rating_requests_from_query = select(RatingRequest).where(RatingRequest.from_user_id == user.id)
        rating_requests_from_result = await session.execute(rating_requests_from_query)
        rating_requests_from = rating_requests_from_result.scalars().all()
        for req in rating_requests_from:
            await session.delete(req)
        
        rating_requests_to_query = select(RatingRequest).where(RatingRequest.to_user_id == user.id)
        rating_requests_to_result = await session.execute(rating_requests_to_query)
        rating_requests_to = rating_requests_to_result.scalars().all()
        for req in rating_requests_to:
            await session.delete(req)
        
        # Удаляем все объявления
        for post in posts:
            await session.delete(post)
        
        # Удаляем пользователя
        await session.delete(user)
        await session.commit()
        
        logger.info(f"Профиль пользователя {user.id} (telegram_id={user.telegram_id}) удален")
    
    await callback.message.edit_text(
        "✅ <b>Профиль удалён</b>\n\n"
        "Все ваши данные были удалены из системы.\n\n"
        "Используйте /start для регистрации заново.",
        parse_mode="HTML"
    )
