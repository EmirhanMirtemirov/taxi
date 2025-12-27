# handlers/callback.py - Обработка откликов на заявки
# Обработка кнопки "Откликнуться" в канале и навигационных callback'ов

from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
import logging

from database import (
    get_user, get_order_by_id, get_active_order,
    take_order
)
from config import CHANNEL_ID
from keyboards import (
    get_main_menu_keyboard,
    get_order_taken_keyboard
)

router = Router()
logger = logging.getLogger(__name__)


# ==================== ОТКЛИК НА ЗАЯВКУ ====================

@router.callback_query(F.data.startswith("respond:"))
async def respond_to_order(callback: CallbackQuery, bot: Bot):
    """Обработка отклика на заявку в канале"""
    # Извлекаем ID заявки
    try:
        order_id = int(callback.data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("❌ Ошибка: неверный ID заявки", show_alert=True)
        return
    
    # Проверяем регистрацию пользователя
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.answer(
            "❌ Вы не зарегистрированы.\n"
            "Сначала зарегистрируйтесь: /start",
            show_alert=True
        )
        return
    
    # Получаем заявку
    order = await get_order_by_id(order_id)
    if not order:
        await callback.answer("❌ Заявка не найдена", show_alert=True)
        return
    
    # Проверяем, что это не своя заявка
    if order["telegram_id"] == callback.from_user.id:
        await callback.answer(
            "❌ Нельзя откликнуться на свою заявку",
            show_alert=True
        )
        return
    
    # Проверяем статус заявки
    if order["status"] != "active":
        await callback.answer(
            "❌ Эта заявка уже неактивна",
            show_alert=True
        )
        return
    
    await callback.answer("✅ Отправляем контакты...")
    
    # Формируем сообщения для обоих участников
    
    # Сообщение автору заявки
    if user["role"] == "driver":
        responder_info = (
            f"👤 {user['name']}\n"
            f"📱 {user['phone']}\n"
            f"🚙 {user['car_model']} | {user['car_number']}"
        )
    else:
        responder_info = (
            f"👤 {user['name']}\n"
            f"📱 {user['phone']}"
        )
    
    author_message = (
        "🔔 <b>Новый отклик на вашу заявку!</b>\n\n"
        f"📍 {order['point_a']} → {order['point_b']}\n\n"
        "<b>Откликнулся:</b>\n"
        f"{responder_info}"
    )
    
    # Сообщение откликнувшемуся
    if order["role"] == "driver":
        author_info = (
            f"👤 {order['name']}\n"
            f"📱 {order['phone']}\n"
            f"🚙 {order['car_model']} | {order['car_number']}"
        )
    else:
        author_info = (
            f"👤 {order['name']}\n"
            f"📱 {order['phone']}"
        )
    
    responder_message = (
        "✅ <b>Вы откликнулись на заявку!</b>\n\n"
        f"📍 {order['point_a']} → {order['point_b']}\n"
        f"💰 {order['price']} сом\n\n"
        "<b>Контакт:</b>\n"
        f"{author_info}"
    )
    
    try:
        # Отправляем автору заявки
        await bot.send_message(
            order["telegram_id"],
            author_message,
            parse_mode="HTML"
        )
        
        # Отправляем откликнувшемуся
        await bot.send_message(
            callback.from_user.id,
            responder_message,
            parse_mode="HTML"
        )
        
        # Обновляем статус заявки
        await take_order(order_id)
        
        # Редактируем сообщение в канале
        if order.get("message_id"):
            try:
                # Формируем новый текст с пометкой "ЗАБРОНИРОВАНО"
                if order["role"] == "driver":
                    new_channel_text = (
                        "✅ <b>ЗАБРОНИРОВАНО</b>\n\n"
                        "🚗 <b>ТАКСИСТ ЕДЕТ</b>\n\n"
                        f"📍 <b>Откуда:</b> {order['point_a']}\n"
                        f"📍 <b>Куда:</b> {order['point_b']}\n"
                        f"💰 <b>Цена:</b> {order['price']} сом\n\n"
                        f"👤 {order['name']}\n"
                        f"🚙 {order['car_model']} | {order['car_number']}"
                    )
                else:
                    new_channel_text = (
                        "✅ <b>ЗАБРОНИРОВАНО</b>\n\n"
                        "👤 <b>ПАССАЖИР ИЩЕТ ТАКСИ</b>\n\n"
                        f"📍 <b>Откуда:</b> {order['point_a']}\n"
                        f"📍 <b>Куда:</b> {order['point_b']}\n"
                        f"💰 <b>Цена:</b> {order['price']} сом\n\n"
                        f"👤 {order['name']}"
                    )
                
                await bot.edit_message_text(
                    chat_id=CHANNEL_ID,
                    message_id=order["message_id"],
                    text=new_channel_text,
                    parse_mode="HTML",
                    reply_markup=get_order_taken_keyboard()
                )
            except Exception as e:
                logger.warning(f"Не удалось обновить сообщение в канале: {e}")
        
        logger.info(
            f"Пользователь {callback.from_user.id} откликнулся на заявку {order_id}"
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обработке отклика: {e}")
        await callback.answer(
            "❌ Произошла ошибка при отправке контактов",
            show_alert=True
        )


# ==================== ВОЗВРАТ В ГЛАВНОЕ МЕНЮ ====================

@router.callback_query(F.data == "main_menu")
async def back_to_main_menu(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню"""
    await callback.answer()
    
    # Очищаем состояние
    await state.clear()
    
    user = await get_user(callback.from_user.id)
    
    if not user:
        await callback.message.edit_text(
            "❌ Вы не зарегистрированы.\n"
            "Используйте /start для регистрации."
        )
        return
    
    # Проверяем наличие активной заявки
    active_order = await get_active_order(callback.from_user.id)
    has_active_order = active_order is not None
    
    await callback.message.edit_text(
        f"🏠 <b>Главное меню</b>\n\n"
        f"Привет, {user['name']}! Что хотите сделать?",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(has_active_order)
    )

