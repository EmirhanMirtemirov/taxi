# handlers/order.py - Создание и управление заявками
# Пошаговое создание заявки и публикация в канал

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta
from typing import Optional
import logging

from states import CreateOrder
from database import (
    get_user, get_active_order, create_order, 
    update_order, cancel_order, get_order_by_id
)
from config import CHANNEL_ID, ORDER_LIFETIME_HOURS
from keyboards import (
    get_cancel_keyboard,
    get_back_cancel_keyboard,
    get_order_confirm_keyboard,
    get_order_exists_keyboard,
    get_active_order_keyboard,
    get_after_publish_keyboard,
    get_order_respond_keyboard,
    get_main_menu_keyboard,
    get_remove_keyboard
)
from utils.message_cleaner import add_message_to_delete, clean_chat

router = Router()
logger = logging.getLogger(__name__)


def validate_price(text: str) -> Optional[int]:
    """Проверяет что цена - положительное число"""
    try:
        price = int(text.replace(" ", ""))
        return price if price > 0 else None
    except ValueError:
        return None


# ==================== НАЧАЛО СОЗДАНИЯ ЗАЯВКИ ====================

@router.callback_query(F.data == "create_order")
async def start_create_order(callback: CallbackQuery, state: FSMContext):
    """Начало создания заявки"""
    await callback.answer()
    
    # Проверяем, зарегистрирован ли пользователь
    user = await get_user(callback.from_user.id)
    if not user:
        await callback.message.edit_text(
            "❌ Вы не зарегистрированы.\n"
            "Используйте /start для регистрации."
        )
        return
    
    # Проверяем, есть ли уже активная заявка
    active_order = await get_active_order(callback.from_user.id)
    if active_order:
        await callback.message.edit_text(
            "⚠️ <b>У вас уже есть активная заявка.</b>\n\n"
            "Вы можете отменить её и создать новую.",
            parse_mode="HTML",
            reply_markup=get_order_exists_keyboard()
        )
        return
    
    # Начинаем создание заявки
    await state.update_data(
        role=user["role"],
        user_name=user["name"],
        user_phone=user["phone"],
        car_model=user.get("car_model"),
        car_number=user.get("car_number"),
        messages_to_delete=[]
    )
    
    # Удаляем предыдущее сообщение
    try:
        await callback.message.delete()
    except:
        pass
    
    # Шаг 1 - откуда
    msg = await callback.message.answer(
        "📍 <b>Создание заявки (1/3)</b>\n\n"
        "Откуда едете?\n"
        "<i>(напишите адрес или район)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(CreateOrder.point_a)


# ==================== ШАГИ СОЗДАНИЯ ЗАЯВКИ ====================

@router.message(CreateOrder.point_a, F.text)
async def process_point_a(message: Message, state: FSMContext, bot: Bot):
    """Обработка точки отправления"""
    if message.text == "❌ Отмена":
        await cancel_order_creation(message, state, bot)
        return
    
    await add_message_to_delete(state, message.message_id)
    
    # Сохраняем точку А
    await state.update_data(point_a=message.text.strip())
    await clean_chat(bot, message.chat.id, state)
    
    # Шаг 2 - куда
    msg = await message.answer(
        "📍 <b>Создание заявки (2/3)</b>\n\n"
        "Куда едете?",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(CreateOrder.point_b)


@router.message(CreateOrder.point_b, F.text)
async def process_point_b(message: Message, state: FSMContext, bot: Bot):
    """Обработка точки назначения"""
    if message.text == "❌ Отмена":
        await cancel_order_creation(message, state, bot)
        return
    
    if message.text == "◀️ Назад":
        await add_message_to_delete(state, message.message_id)
        await clean_chat(bot, message.chat.id, state)
        
        msg = await message.answer(
            "📍 <b>Создание заявки (1/3)</b>\n\n"
            "Откуда едете?\n"
            "<i>(напишите адрес или район)</i>",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        await state.set_state(CreateOrder.point_a)
        return
    
    await add_message_to_delete(state, message.message_id)
    
    # Сохраняем точку Б
    await state.update_data(point_b=message.text.strip())
    await clean_chat(bot, message.chat.id, state)
    
    # Шаг 3 - цена
    msg = await message.answer(
        "💰 <b>Создание заявки (3/3)</b>\n\n"
        "Укажите цену (в сомах):",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(CreateOrder.price)


@router.message(CreateOrder.price, F.text)
async def process_price(message: Message, state: FSMContext, bot: Bot):
    """Обработка цены"""
    if message.text == "❌ Отмена":
        await cancel_order_creation(message, state, bot)
        return
    
    if message.text == "◀️ Назад":
        await add_message_to_delete(state, message.message_id)
        await clean_chat(bot, message.chat.id, state)
        
        msg = await message.answer(
            "📍 <b>Создание заявки (2/3)</b>\n\n"
            "Куда едете?",
            parse_mode="HTML",
            reply_markup=get_back_cancel_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        await state.set_state(CreateOrder.point_b)
        return
    
    await add_message_to_delete(state, message.message_id)
    
    # Валидация цены
    price = validate_price(message.text)
    if not price:
        msg = await message.answer(
            "❌ Укажите корректную цену (целое положительное число).\n\n"
            "Попробуйте ещё раз:",
            reply_markup=get_back_cancel_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        return
    
    # Сохраняем цену
    await state.update_data(price=price)
    await clean_chat(bot, message.chat.id, state)
    
    # Показываем подтверждение
    await show_order_confirmation(message, state)


async def show_order_confirmation(message: Message, state: FSMContext):
    """Показать превью заявки для подтверждения"""
    data = await state.get_data()
    
    if data["role"] == "driver":
        # Заявка от таксиста
        confirm_text = (
            "📋 <b>Проверьте вашу заявку:</b>\n\n"
            "🚗 <b>ТИП:</b> Таксист едет\n\n"
            f"📍 <b>Откуда:</b> {data['point_a']}\n"
            f"📍 <b>Куда:</b> {data['point_b']}\n"
            f"💰 <b>Цена:</b> {data['price']} сом\n\n"
            f"👤 {data['user_name']}\n"
            f"🚙 {data['car_model']} | {data['car_number']}\n\n"
            "Опубликовать в канал?"
        )
    else:
        # Заявка от пассажира
        confirm_text = (
            "📋 <b>Проверьте вашу заявку:</b>\n\n"
            "👤 <b>ТИП:</b> Пассажир ищет такси\n\n"
            f"📍 <b>Откуда:</b> {data['point_a']}\n"
            f"📍 <b>Куда:</b> {data['point_b']}\n"
            f"💰 <b>Цена:</b> {data['price']} сом\n\n"
            f"👤 {data['user_name']}\n"
            f"📱 {data['user_phone']}\n\n"
            "Опубликовать в канал?"
        )
    
    await message.answer(
        confirm_text,
        parse_mode="HTML",
        reply_markup=get_order_confirm_keyboard()
    )
    
    await state.set_state(CreateOrder.confirm)


# ==================== ПУБЛИКАЦИЯ ЗАЯВКИ ====================

@router.callback_query(F.data == "order:publish")
async def publish_order(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Публикация заявки в канал"""
    await callback.answer("Публикую заявку...")
    
    data = await state.get_data()
    user = await get_user(callback.from_user.id)
    
    if not user:
        await callback.message.edit_text("❌ Ошибка: пользователь не найден.")
        await state.clear()
        return
    
    # Формируем текст для канала
    if data["role"] == "driver":
        channel_text = (
            "🚗 <b>ТАКСИСТ ЕДЕТ</b>\n\n"
            f"📍 <b>Откуда:</b> {data['point_a']}\n"
            f"📍 <b>Куда:</b> {data['point_b']}\n"
            f"💰 <b>Цена:</b> {data['price']} сом\n\n"
            f"👤 {data['user_name']}\n"
            f"🚙 {data['car_model']} | {data['car_number']}\n\n"
            f"⏰ Истекает через {ORDER_LIFETIME_HOURS} часа"
        )
    else:
        channel_text = (
            "👤 <b>ПАССАЖИР ИЩЕТ ТАКСИ</b>\n\n"
            f"📍 <b>Откуда:</b> {data['point_a']}\n"
            f"📍 <b>Куда:</b> {data['point_b']}\n"
            f"💰 <b>Цена:</b> {data['price']} сом\n\n"
            f"👤 {data['user_name']}\n\n"
            f"⏰ Истекает через {ORDER_LIFETIME_HOURS} часа"
        )
    
    try:
        # Создаём заявку в базе
        order_id = await create_order(
            telegram_id=callback.from_user.id,
            role=data["role"],
            point_a=data["point_a"],
            point_b=data["point_b"],
            price=data["price"]
        )
        
        # Публикуем в канал
        channel_msg = await bot.send_message(
            CHANNEL_ID,
            channel_text,
            parse_mode="HTML",
            reply_markup=get_order_respond_keyboard(order_id)
        )
        
        # Сохраняем ID сообщения в канале
        await update_order(order_id, message_id=channel_msg.message_id)
        
        # Очищаем состояние
        await state.clear()
        
        # Удаляем сообщение с подтверждением
        try:
            await callback.message.delete()
        except:
            pass
        
        # Уведомляем пользователя
        await callback.message.answer(
            "✅ <b>Заявка опубликована!</b>\n\n"
            "Ожидайте откликов. Вам придёт уведомление, когда кто-то откликнется.",
            parse_mode="HTML",
            reply_markup=get_after_publish_keyboard()
        )
        
        logger.info(f"Заявка {order_id} опубликована пользователем {callback.from_user.id}")
        
    except Exception as e:
        logger.error(f"Ошибка при публикации заявки: {e}")
        await callback.message.edit_text(
            "❌ Произошла ошибка при публикации заявки.\n"
            "Попробуйте позже."
        )
        await state.clear()


# ==================== РЕДАКТИРОВАНИЕ ЗАЯВКИ ====================

@router.callback_query(F.data == "order:edit_route")
async def edit_order_route(callback: CallbackQuery, state: FSMContext):
    """Редактирование маршрута заявки"""
    await callback.answer()
    
    try:
        await callback.message.delete()
    except:
        pass
    
    msg = await callback.message.answer(
        "📍 <b>Редактирование маршрута</b>\n\n"
        "Откуда едете?\n"
        "<i>(напишите адрес или район)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(CreateOrder.point_a)


@router.callback_query(F.data == "order:edit_price")
async def edit_order_price(callback: CallbackQuery, state: FSMContext):
    """Редактирование цены заявки"""
    await callback.answer()
    
    try:
        await callback.message.delete()
    except:
        pass
    
    msg = await callback.message.answer(
        "💰 <b>Редактирование цены</b>\n\n"
        "Укажите новую цену (в сомах):",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(CreateOrder.price)


@router.callback_query(F.data == "order:cancel")
async def cancel_order_callback(callback: CallbackQuery, state: FSMContext):
    """Отмена создания заявки через inline кнопку"""
    await callback.answer("Создание заявки отменено")
    await state.clear()
    
    try:
        await callback.message.delete()
    except:
        pass
    
    # Показываем главное меню
    user = await get_user(callback.from_user.id)
    if user:
        active_order = await get_active_order(callback.from_user.id)
        await callback.message.answer(
            f"🏠 <b>Главное меню</b>\n\n"
            f"Привет, {user['name']}! Что хотите сделать?",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(active_order is not None)
        )


# ==================== МОЯ АКТИВНАЯ ЗАЯВКА ====================

@router.callback_query(F.data == "my_order")
async def show_my_order(callback: CallbackQuery):
    """Показать активную заявку пользователя"""
    await callback.answer()
    
    order = await get_active_order(callback.from_user.id)
    
    if not order:
        await callback.message.edit_text(
            "📋 У вас нет активных заявок.",
            reply_markup=get_main_menu_keyboard(False)
        )
        return
    
    # Вычисляем оставшееся время
    expires_at = datetime.fromisoformat(order["expires_at"])
    now = datetime.utcnow()
    remaining = expires_at - now
    
    if remaining.total_seconds() > 0:
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        time_left = f"{hours}ч {minutes}мин"
    else:
        time_left = "скоро истечёт"
    
    order_text = (
        "📋 <b>Ваша активная заявка:</b>\n\n"
        f"📍 <b>Откуда:</b> {order['point_a']}\n"
        f"📍 <b>Куда:</b> {order['point_b']}\n"
        f"💰 <b>Цена:</b> {order['price']} сом\n\n"
        f"⏰ <b>Истекает:</b> через {time_left}\n"
        f"📊 <b>Статус:</b> Активна"
    )
    
    await callback.message.edit_text(
        order_text,
        parse_mode="HTML",
        reply_markup=get_active_order_keyboard()
    )


@router.callback_query(F.data == "cancel_order")
async def cancel_active_order(callback: CallbackQuery, bot: Bot):
    """Отмена активной заявки"""
    order = await get_active_order(callback.from_user.id)
    
    if not order:
        await callback.answer("Заявка не найдена")
        return
    
    await callback.answer("Заявка отменена")
    
    # Удаляем сообщение из канала
    if order.get("message_id"):
        try:
            await bot.delete_message(CHANNEL_ID, order["message_id"])
        except Exception as e:
            logger.warning(f"Не удалось удалить сообщение из канала: {e}")
    
    # Отменяем заявку в базе
    await cancel_order(order["id"])
    
    # Показываем главное меню
    user = await get_user(callback.from_user.id)
    await callback.message.edit_text(
        "✅ Заявка отменена.\n\n"
        f"🏠 <b>Главное меню</b>\n\n"
        f"Привет, {user['name']}! Что хотите сделать?",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(False)
    )


# ==================== ОТМЕНА СОЗДАНИЯ ====================

async def cancel_order_creation(message: Message, state: FSMContext, bot: Bot):
    """Отмена создания заявки через Reply кнопку"""
    await add_message_to_delete(state, message.message_id)
    await clean_chat(bot, message.chat.id, state)
    await state.clear()
    
    # Показываем главное меню
    user = await get_user(message.from_user.id)
    if user:
        active_order = await get_active_order(message.from_user.id)
        await message.answer(
            f"🏠 <b>Главное меню</b>\n\n"
            f"Привет, {user['name']}! Что хотите сделать?",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(active_order is not None)
        )

