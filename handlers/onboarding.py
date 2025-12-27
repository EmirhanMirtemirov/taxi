# handlers/onboarding.py - Регистрация пользователей
# Пошаговый онбординг для таксистов и пассажиров

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import re
import logging

from states import DriverOnboarding, PassengerOnboarding
from database import create_user, get_user, get_active_order
from keyboards import (
    get_cancel_keyboard,
    get_back_cancel_keyboard,
    get_contact_keyboard,
    get_driver_confirm_keyboard,
    get_passenger_confirm_keyboard,
    get_main_menu_keyboard,
    get_remove_keyboard
)
from utils.message_cleaner import add_message_to_delete, clean_chat

router = Router()
logger = logging.getLogger(__name__)


# ==================== ВАЛИДАЦИЯ ====================

def validate_phone(phone: str) -> bool:
    """Проверяет формат телефона: +996XXXXXXXXX или 0XXXXXXXXX"""
    pattern = r'^(\+996\d{9}|0\d{9})$'
    return bool(re.match(pattern, phone.replace(" ", "").replace("-", "")))


def format_phone(phone: str) -> str:
    """Приводит телефон к формату +996XXXXXXXXX"""
    phone = phone.replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        return "+996" + phone[1:]
    return phone


# ==================== ВЫБОР РОЛИ ====================

@router.callback_query(F.data == "role:driver")
async def start_driver_onboarding(callback: CallbackQuery, state: FSMContext):
    """Начало регистрации таксиста"""
    await callback.answer()
    
    # Сохраняем роль
    await state.update_data(role="driver", messages_to_delete=[])
    
    # Удаляем сообщение с выбором роли
    try:
        await callback.message.delete()
    except:
        pass
    
    # Первый шаг - имя
    msg = await callback.message.answer(
        "📝 <b>Регистрация таксиста (1/4)</b>\n\n"
        "Введите ваше имя:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(DriverOnboarding.name)


@router.callback_query(F.data == "role:passenger")
async def start_passenger_onboarding(callback: CallbackQuery, state: FSMContext):
    """Начало регистрации пассажира"""
    await callback.answer()
    
    # Сохраняем роль
    await state.update_data(role="passenger", messages_to_delete=[])
    
    # Удаляем сообщение с выбором роли
    try:
        await callback.message.delete()
    except:
        pass
    
    # Первый шаг - имя
    msg = await callback.message.answer(
        "📝 <b>Регистрация пассажира (1/2)</b>\n\n"
        "Введите ваше имя:",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(PassengerOnboarding.name)


# ==================== ОНБОРДИНГ ТАКСИСТА ====================

@router.message(DriverOnboarding.name, F.text)
async def process_driver_name(message: Message, state: FSMContext, bot: Bot):
    """Обработка имени таксиста"""
    if message.text == "❌ Отмена":
        await cancel_onboarding(message, state, bot)
        return
    
    # Сохраняем сообщение пользователя для удаления
    await add_message_to_delete(state, message.message_id)
    
    # Сохраняем имя
    await state.update_data(name=message.text.strip())
    
    # Удаляем предыдущие сообщения
    await clean_chat(bot, message.chat.id, state)
    
    # Шаг 2 - телефон
    msg = await message.answer(
        "📝 <b>Регистрация таксиста (2/4)</b>\n\n"
        "Отправьте номер телефона:",
        parse_mode="HTML",
        reply_markup=get_contact_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(DriverOnboarding.phone)


@router.message(DriverOnboarding.phone)
async def process_driver_phone(message: Message, state: FSMContext, bot: Bot):
    """Обработка телефона таксиста"""
    # Проверяем кнопки навигации
    if message.text == "❌ Отмена":
        await cancel_onboarding(message, state, bot)
        return
    
    if message.text == "◀️ Назад":
        await add_message_to_delete(state, message.message_id)
        await clean_chat(bot, message.chat.id, state)
        
        msg = await message.answer(
            "📝 <b>Регистрация таксиста (1/4)</b>\n\n"
            "Введите ваше имя:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        await state.set_state(DriverOnboarding.name)
        return
    
    # Обрабатываем контакт или текст
    phone = None
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    elif message.text:
        if validate_phone(message.text):
            phone = format_phone(message.text)
    
    await add_message_to_delete(state, message.message_id)
    
    if not phone:
        msg = await message.answer(
            "❌ Неверный формат телефона.\n"
            "Используйте формат: +996XXXXXXXXX или 0XXXXXXXXX\n\n"
            "Попробуйте ещё раз или нажмите кнопку 📱",
            reply_markup=get_contact_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        return
    
    # Сохраняем телефон
    await state.update_data(phone=phone)
    await clean_chat(bot, message.chat.id, state)
    
    # Шаг 3 - марка авто
    msg = await message.answer(
        "📝 <b>Регистрация таксиста (3/4)</b>\n\n"
        "Введите марку и модель автомобиля:\n"
        "<i>(например: Toyota Camry)</i>",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(DriverOnboarding.car_model)


@router.message(DriverOnboarding.car_model, F.text)
async def process_driver_car_model(message: Message, state: FSMContext, bot: Bot):
    """Обработка марки авто"""
    if message.text == "❌ Отмена":
        await cancel_onboarding(message, state, bot)
        return
    
    if message.text == "◀️ Назад":
        await add_message_to_delete(state, message.message_id)
        await clean_chat(bot, message.chat.id, state)
        
        msg = await message.answer(
            "📝 <b>Регистрация таксиста (2/4)</b>\n\n"
            "Отправьте номер телефона:",
            parse_mode="HTML",
            reply_markup=get_contact_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        await state.set_state(DriverOnboarding.phone)
        return
    
    await add_message_to_delete(state, message.message_id)
    
    # Сохраняем марку
    await state.update_data(car_model=message.text.strip())
    await clean_chat(bot, message.chat.id, state)
    
    # Шаг 4 - гос. номер
    msg = await message.answer(
        "📝 <b>Регистрация таксиста (4/4)</b>\n\n"
        "Введите гос. номер автомобиля:\n"
        "<i>(например: 01KG777ABC)</i>",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(DriverOnboarding.car_number)


@router.message(DriverOnboarding.car_number, F.text)
async def process_driver_car_number(message: Message, state: FSMContext, bot: Bot):
    """Обработка гос. номера"""
    if message.text == "❌ Отмена":
        await cancel_onboarding(message, state, bot)
        return
    
    if message.text == "◀️ Назад":
        await add_message_to_delete(state, message.message_id)
        await clean_chat(bot, message.chat.id, state)
        
        msg = await message.answer(
            "📝 <b>Регистрация таксиста (3/4)</b>\n\n"
            "Введите марку и модель автомобиля:\n"
            "<i>(например: Toyota Camry)</i>",
            parse_mode="HTML",
            reply_markup=get_back_cancel_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        await state.set_state(DriverOnboarding.car_model)
        return
    
    await add_message_to_delete(state, message.message_id)
    
    # Сохраняем номер
    await state.update_data(car_number=message.text.strip().upper())
    await clean_chat(bot, message.chat.id, state)
    
    # Показываем подтверждение
    await show_driver_confirmation(message, state)


async def show_driver_confirmation(message: Message, state: FSMContext):
    """Показать карточку подтверждения для таксиста"""
    data = await state.get_data()
    
    confirm_text = (
        "✅ <b>Проверьте ваши данные:</b>\n\n"
        f"👤 Имя: {data['name']}\n"
        f"📱 Телефон: {data['phone']}\n"
        f"🚙 Авто: {data['car_model']}\n"
        f"🔢 Номер: {data['car_number']}\n\n"
        "Всё верно?"
    )
    
    await message.answer(
        confirm_text,
        parse_mode="HTML",
        reply_markup=get_driver_confirm_keyboard()
    )
    
    await state.set_state(DriverOnboarding.confirm)


# ==================== ОНБОРДИНГ ПАССАЖИРА ====================

@router.message(PassengerOnboarding.name, F.text)
async def process_passenger_name(message: Message, state: FSMContext, bot: Bot):
    """Обработка имени пассажира"""
    if message.text == "❌ Отмена":
        await cancel_onboarding(message, state, bot)
        return
    
    await add_message_to_delete(state, message.message_id)
    
    # Сохраняем имя
    await state.update_data(name=message.text.strip())
    await clean_chat(bot, message.chat.id, state)
    
    # Шаг 2 - телефон
    msg = await message.answer(
        "📝 <b>Регистрация пассажира (2/2)</b>\n\n"
        "Отправьте номер телефона:",
        parse_mode="HTML",
        reply_markup=get_contact_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(PassengerOnboarding.phone)


@router.message(PassengerOnboarding.phone)
async def process_passenger_phone(message: Message, state: FSMContext, bot: Bot):
    """Обработка телефона пассажира"""
    if message.text == "❌ Отмена":
        await cancel_onboarding(message, state, bot)
        return
    
    if message.text == "◀️ Назад":
        await add_message_to_delete(state, message.message_id)
        await clean_chat(bot, message.chat.id, state)
        
        msg = await message.answer(
            "📝 <b>Регистрация пассажира (1/2)</b>\n\n"
            "Введите ваше имя:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        await state.set_state(PassengerOnboarding.name)
        return
    
    # Обрабатываем контакт или текст
    phone = None
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    elif message.text:
        if validate_phone(message.text):
            phone = format_phone(message.text)
    
    await add_message_to_delete(state, message.message_id)
    
    if not phone:
        msg = await message.answer(
            "❌ Неверный формат телефона.\n"
            "Используйте формат: +996XXXXXXXXX или 0XXXXXXXXX\n\n"
            "Попробуйте ещё раз или нажмите кнопку 📱",
            reply_markup=get_contact_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        return
    
    # Сохраняем телефон
    await state.update_data(phone=phone)
    await clean_chat(bot, message.chat.id, state)
    
    # Показываем подтверждение
    await show_passenger_confirmation(message, state)


async def show_passenger_confirmation(message: Message, state: FSMContext):
    """Показать карточку подтверждения для пассажира"""
    data = await state.get_data()
    
    confirm_text = (
        "✅ <b>Проверьте ваши данные:</b>\n\n"
        f"👤 Имя: {data['name']}\n"
        f"📱 Телефон: {data['phone']}\n\n"
        "Всё верно?"
    )
    
    await message.answer(
        confirm_text,
        parse_mode="HTML",
        reply_markup=get_passenger_confirm_keyboard()
    )
    
    await state.set_state(PassengerOnboarding.confirm)


# ==================== ПОДТВЕРЖДЕНИЕ И РЕДАКТИРОВАНИЕ ====================

@router.callback_query(F.data == "onboard:confirm")
async def confirm_onboarding(callback: CallbackQuery, state: FSMContext):
    """Подтверждение регистрации"""
    await callback.answer("✅ Регистрация завершена!")
    
    data = await state.get_data()
    
    # Создаём пользователя в базе
    await create_user(
        telegram_id=callback.from_user.id,
        role=data["role"],
        name=data["name"],
        phone=data["phone"],
        car_model=data.get("car_model"),
        car_number=data.get("car_number")
    )
    
    # Очищаем состояние
    await state.clear()
    
    # Удаляем сообщение с подтверждением
    try:
        await callback.message.delete()
    except:
        pass
    
    # Показываем главное меню
    await callback.message.answer(
        f"🎉 <b>Добро пожаловать, {data['name']}!</b>\n\n"
        "Регистрация успешно завершена.\n"
        "Теперь вы можете создавать заявки и откликаться на заявки других.",
        parse_mode="HTML",
        reply_markup=get_remove_keyboard()
    )
    
    # Показываем меню
    await callback.message.answer(
        "🏠 <b>Главное меню</b>\n\n"
        "Что хотите сделать?",
        parse_mode="HTML",
        reply_markup=get_main_menu_keyboard(False)
    )


@router.callback_query(F.data == "onboard:cancel")
async def cancel_onboarding_callback(callback: CallbackQuery, state: FSMContext):
    """Отмена регистрации через inline кнопку"""
    await callback.answer("Регистрация отменена")
    await state.clear()
    
    try:
        await callback.message.delete()
    except:
        pass
    
    # Возвращаем к выбору роли
    from keyboards import get_role_keyboard
    await callback.message.answer(
        "🚕 <b>Добро пожаловать в TaxiBot!</b>\n\n"
        "Сервис для поиска попутчиков и такси в городе.\n\n"
        "<b>Выберите кто вы:</b>",
        parse_mode="HTML",
        reply_markup=get_role_keyboard()
    )


@router.callback_query(F.data == "onboard:edit_name")
async def edit_name_onboarding(callback: CallbackQuery, state: FSMContext):
    """Редактирование имени в процессе онбординга"""
    await callback.answer()
    
    data = await state.get_data()
    role = data.get("role", "passenger")
    
    try:
        await callback.message.delete()
    except:
        pass
    
    if role == "driver":
        msg = await callback.message.answer(
            "📝 <b>Редактирование имени</b>\n\n"
            f"Текущее имя: {data.get('name', '')}\n\n"
            "Введите новое имя:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(DriverOnboarding.name)
    else:
        msg = await callback.message.answer(
            "📝 <b>Редактирование имени</b>\n\n"
            f"Текущее имя: {data.get('name', '')}\n\n"
            "Введите новое имя:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        await state.set_state(PassengerOnboarding.name)
    
    await add_message_to_delete(state, msg.message_id)


@router.callback_query(F.data == "onboard:edit_phone")
async def edit_phone_onboarding(callback: CallbackQuery, state: FSMContext):
    """Редактирование телефона в процессе онбординга"""
    await callback.answer()
    
    data = await state.get_data()
    role = data.get("role", "passenger")
    
    try:
        await callback.message.delete()
    except:
        pass
    
    if role == "driver":
        msg = await callback.message.answer(
            "📝 <b>Редактирование телефона</b>\n\n"
            f"Текущий телефон: {data.get('phone', '')}\n\n"
            "Отправьте новый номер:",
            parse_mode="HTML",
            reply_markup=get_contact_keyboard()
        )
        await state.set_state(DriverOnboarding.phone)
    else:
        msg = await callback.message.answer(
            "📝 <b>Редактирование телефона</b>\n\n"
            f"Текущий телефон: {data.get('phone', '')}\n\n"
            "Отправьте новый номер:",
            parse_mode="HTML",
            reply_markup=get_contact_keyboard()
        )
        await state.set_state(PassengerOnboarding.phone)
    
    await add_message_to_delete(state, msg.message_id)


@router.callback_query(F.data == "onboard:edit_car_model")
async def edit_car_model_onboarding(callback: CallbackQuery, state: FSMContext):
    """Редактирование марки авто в процессе онбординга"""
    await callback.answer()
    
    data = await state.get_data()
    
    try:
        await callback.message.delete()
    except:
        pass
    
    msg = await callback.message.answer(
        "📝 <b>Редактирование автомобиля</b>\n\n"
        f"Текущее авто: {data.get('car_model', '')}\n\n"
        "Введите новую марку и модель:",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(DriverOnboarding.car_model)


@router.callback_query(F.data == "onboard:edit_car_number")
async def edit_car_number_onboarding(callback: CallbackQuery, state: FSMContext):
    """Редактирование гос. номера в процессе онбординга"""
    await callback.answer()
    
    data = await state.get_data()
    
    try:
        await callback.message.delete()
    except:
        pass
    
    msg = await callback.message.answer(
        "📝 <b>Редактирование гос. номера</b>\n\n"
        f"Текущий номер: {data.get('car_number', '')}\n\n"
        "Введите новый гос. номер:",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard()
    )
    
    await add_message_to_delete(state, msg.message_id)
    await state.set_state(DriverOnboarding.car_number)


# ==================== ОТМЕНА РЕГИСТРАЦИИ ====================

async def cancel_onboarding(message: Message, state: FSMContext, bot: Bot):
    """Отмена регистрации через Reply кнопку"""
    await add_message_to_delete(state, message.message_id)
    await clean_chat(bot, message.chat.id, state)
    await state.clear()
    
    # Возвращаем к выбору роли
    from keyboards import get_role_keyboard
    await message.answer(
        "🚕 <b>Добро пожаловать в TaxiBot!</b>\n\n"
        "Сервис для поиска попутчиков и такси в городе.\n\n"
        "<b>Выберите кто вы:</b>",
        parse_mode="HTML",
        reply_markup=get_role_keyboard()
    )

