# handlers/registration.py - Регистрация пользователей
# Выбор роли и ввод телефона

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
import re
import logging

from states import Registration
from database.db import get_session
from database.models import User
from sqlalchemy import select
from utils.message_cleaner import add_message_to_delete, clean_chat
from keyboards import (
    get_phone_keyboard, 
    get_main_menu_keyboard, 
    get_remove_keyboard,
    get_cancel_keyboard
)
from services.car_photo_validator import validate_and_extract_car_info

router = Router()
logger = logging.getLogger(__name__)


def validate_phone(phone: str) -> bool:
    """Проверяет формат телефона: +996XXXXXXXXX"""
    pattern = r'^\+996\d{9}$'
    return bool(re.match(pattern, phone.replace(" ", "").replace("-", "")))


def format_phone(phone: str) -> str:
    """Приводит телефон к формату +996XXXXXXXXX"""
    phone = phone.replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        return "+996" + phone[1:]
    if not phone.startswith("+"):
        return "+" + phone
    return phone


@router.callback_query(F.data.startswith("role:"))
async def choose_role(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Обработка выбора роли"""
    await callback.answer()
    
    # Очищаем предыдущие сообщения перед началом регистрации
    await clean_chat(bot, callback.from_user.id, state)
    await state.update_data(messages_to_delete=[])
    
    role = callback.data.split(":")[1]  # 'driver' или 'passenger'
    
    # Сохраняем роль в state
    await state.update_data(role=role)
    
    # Удаляем сообщение с выбором
    try:
        await callback.message.delete()
    except:
        pass
    
    # Запрашиваем телефон
    role_text = "водителя" if role == "driver" else "пассажира"
    
    msg = await callback.message.answer(
        f"📱 <b>Регистрация {role_text}</b>\n\n"
        "Отправьте номер телефона:\n"
        "<i>Формат: +996XXXXXXXXX</i>",
        parse_mode="HTML",
        reply_markup=get_phone_keyboard()
    )
    await add_message_to_delete(state, msg.message_id)
    
    await state.set_state(Registration.entering_phone)


@router.message(Registration.entering_phone)
async def process_phone(message: Message, state: FSMContext, bot: Bot):
    """Обработка ввода телефона"""
    # Проверяем кнопку отмены
    if message.text == "❌ Отмена":
        await clean_chat(bot, message.chat.id, state)
        await state.clear()
        await message.answer(
            "Регистрация отменена.",
            reply_markup=get_remove_keyboard()
        )
        # Возвращаем к выбору роли
        from keyboards import get_role_keyboard
        await message.answer(
            "🚗 <b>Добро пожаловать в PoputchikBot!</b>\n\n"
            "<b>Выберите кто вы:</b>",
            parse_mode="HTML",
            reply_markup=get_role_keyboard()
        )
        return
    
    # Обрабатываем контакт или текст
    phone = None
    
    if message.contact:
        phone = message.contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
    elif message.text:
        phone = format_phone(message.text)
    
    # Валидация
    if not phone or not validate_phone(phone):
        await add_message_to_delete(state, message.message_id)
        msg = await message.answer(
            "❌ Неверный формат телефона.\n"
            "Используйте формат: <b>+996XXXXXXXXX</b>\n\n"
            "Попробуйте ещё раз или нажмите кнопку 📱",
            parse_mode="HTML",
            reply_markup=get_phone_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        return
    
    # Добавляем сообщение пользователя в список для удаления
    await add_message_to_delete(state, message.message_id)
    
    # Получаем данные из state
    data = await state.get_data()
    role = data.get("role", "passenger")
    
    # Сохраняем телефон в state
    await state.update_data(phone=phone)
    
    # Для водителей запрашиваем фото автомобиля
    if role == "driver":
        await clean_chat(bot, message.chat.id, state)
        msg = await message.answer(
            "📸 <b>Регистрация водителя</b>\n\n"
            "Отправьте фото вашего автомобиля.\n"
            "На фото должен быть виден номер автомобиля.\n\n"
            "<i>Бот автоматически проверит фото и попытается распознать номер.</i>",
            parse_mode="HTML"
        )
        await add_message_to_delete(state, msg.message_id)
        await state.set_state(Registration.uploading_car_photo)
        return
    
    # Для пассажиров сразу завершаем регистрацию
    await finish_registration(message, state, bot)


# ==================== ОБРАБОТКА ФОТО АВТОМОБИЛЯ ====================

@router.message(Registration.uploading_car_photo, F.photo)
async def process_car_photo(message: Message, state: FSMContext, bot: Bot):
    """Обработка фото автомобиля"""
    await add_message_to_delete(state, message.message_id)
    
    # Берем самое большое фото
    photo = message.photo[-1]
    photo_file_id = photo.file_id
    
    # Показываем, что обрабатываем
    processing_msg = await message.answer("⏳ Проверяю фото...")
    await add_message_to_delete(state, processing_msg.message_id)
    
    # Проверяем через OpenAI
    validation_result = await validate_and_extract_car_info(photo_file_id, bot)
    
    if not validation_result['is_valid']:
        # Фото не прошло проверку
        await clean_chat(bot, message.chat.id, state)
        msg = await message.answer(
            validation_result['message'],
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        return
    
    # Сохраняем file_id в state
    await state.update_data(car_photo_file_id=photo_file_id)
    
    # Если номер распознан - проверяем уникальность
    if validation_result['car_number']:
        car_number = validation_result['car_number']
        
        # Проверяем, не занят ли номер
        async with get_session() as session:
            existing_user_query = select(User).where(
                User.car_number == car_number,
                User.telegram_id != message.from_user.id  # Исключаем текущего пользователя
            )
            existing_user_result = await session.execute(existing_user_query)
            existing_user = existing_user_result.scalars().first()  # Используем first() вместо scalar_one_or_none() для избежания MultipleResultsFound
            
            if existing_user:
                # Номер уже занят
                await clean_chat(bot, message.chat.id, state)
                msg = await message.answer(
                    f"❌ <b>Номер автомобиля уже зарегистрирован!</b>\n\n"
                    f"Номер <b>{car_number}</b> уже используется другим пользователем.\n\n"
                    "Пожалуйста, отправьте другое фото автомобиля или введите номер вручную.",
                    parse_mode="HTML",
                    reply_markup=get_cancel_keyboard()
                )
                await add_message_to_delete(state, msg.message_id)
                return
        
        # Номер свободен - сохраняем и завершаем
        await state.update_data(car_number=car_number)
        await clean_chat(bot, message.chat.id, state)
        msg = await message.answer(
            validation_result['message'],
            parse_mode="HTML"
        )
        await add_message_to_delete(state, msg.message_id)
        await finish_registration(message, state, bot)
    else:
        # Номер не распознан - просим ввести вручную
        await clean_chat(bot, message.chat.id, state)
        msg = await message.answer(
            validation_result['message'] + "\n\n"
            "Введите номер автомобиля:",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        await state.set_state(Registration.entering_car_number)


@router.message(Registration.uploading_car_photo)
async def process_car_photo_invalid(message: Message, state: FSMContext, bot: Bot):
    """Обработка некорректного ввода при загрузке фото"""
    await add_message_to_delete(state, message.message_id)
    msg = await message.answer(
        "❌ Пожалуйста, отправьте фото автомобиля.\n"
        "Используйте кнопку 📷 для отправки фото.",
        reply_markup=get_cancel_keyboard()
    )
    await add_message_to_delete(state, msg.message_id)


# ==================== ОБРАБОТКА ВВОДА НОМЕРА ВРУЧНУЮ ====================

@router.message(Registration.entering_car_number, F.text)
async def process_car_number(message: Message, state: FSMContext, bot: Bot):
    """Обработка ввода номера автомобиля вручную"""
    if message.text == "❌ Отмена":
        await clean_chat(bot, message.chat.id, state)
        await state.clear()
        await message.answer(
            "Регистрация отменена.",
            reply_markup=get_remove_keyboard()
        )
        from keyboards import get_role_keyboard
        await message.answer(
            "🚗 <b>Добро пожаловать в PoputchikBot!</b>\n\n"
            "<b>Выберите кто вы:</b>",
            parse_mode="HTML",
            reply_markup=get_role_keyboard()
        )
        return
    
    await add_message_to_delete(state, message.message_id)
    
    # Очищаем номер от лишних символов
    car_number = message.text.upper().strip()
    car_number = ''.join(c for c in car_number if c.isalnum())
    
    if len(car_number) < 3:
        await clean_chat(bot, message.chat.id, state)
        msg = await message.answer(
            "❌ Номер слишком короткий. Введите номер автомобиля:",
            reply_markup=get_cancel_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        return
    
    # Проверяем, не занят ли номер
    async with get_session() as session:
        existing_user_query = select(User).where(
            User.car_number == car_number,
            User.telegram_id != message.from_user.id  # Исключаем текущего пользователя
        )
        existing_user_result = await session.execute(existing_user_query)
        existing_user = existing_user_result.scalars().first()  # Используем first() вместо scalar_one_or_none() для избежания MultipleResultsFound
        
        if existing_user:
            # Номер уже занят
            await clean_chat(bot, message.chat.id, state)
            msg = await message.answer(
                f"❌ <b>Номер автомобиля уже зарегистрирован!</b>\n\n"
                f"Номер <b>{car_number}</b> уже используется другим пользователем.\n\n"
                "Пожалуйста, введите другой номер автомобиля:",
                parse_mode="HTML",
                reply_markup=get_cancel_keyboard()
            )
            await add_message_to_delete(state, msg.message_id)
            return
    
    # Номер свободен - сохраняем и завершаем
    await state.update_data(car_number=car_number)
    await clean_chat(bot, message.chat.id, state)
    await finish_registration(message, state, bot)


# ==================== ЗАВЕРШЕНИЕ РЕГИСТРАЦИИ ====================

async def finish_registration(message: Message, state: FSMContext, bot: Bot):
    """Завершение регистрации с сохранением всех данных"""
    data = await state.get_data()
    role = data.get("role", "passenger")
    phone = data.get("phone")
    car_photo_file_id = data.get("car_photo_file_id")
    car_number = data.get("car_number")
    
    # Создаем или обновляем пользователя в БД
    async with get_session() as session:
        user_query = select(User).where(User.telegram_id == message.from_user.id)
        user_result = await session.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if user:
            # Обновляем данные
            user.phone = phone  # Обновляем телефон на случай, если он изменился
            user.car_photo_file_id = car_photo_file_id
            user.car_number = car_number
            await session.commit()
            logger.info(f"Обновлен пользователь: {message.from_user.id}, фото: {bool(car_photo_file_id)}, номер: {car_number}")
        else:
            # Создаем нового пользователя
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                role=role,
                phone=phone,
                car_photo_file_id=car_photo_file_id,
                car_number=car_number
            )
            session.add(user)
            await session.commit()
            logger.info(f"Создан пользователь: {message.from_user.id}, роль: {role}")
    
    # Проверяем, нужно ли показать объявление после регистрации
    post_id_to_show = data.get("post_id_after_registration")
    create_post_after_reg = data.get("create_post_after_registration", False)
    
    # Очищаем состояние
    await state.clear()
    
    # Убираем Reply клавиатуру
    await message.answer(
        "✅ Регистрация завершена!",
        reply_markup=get_remove_keyboard()
    )
    
    # Если был сохранён post_id - показываем объявление
    if post_id_to_show:
        from handlers.start import show_post_from_channel
        await show_post_from_channel(message, post_id_to_show)
    elif create_post_after_reg:
        # Если был запрос на создание объявления - открываем создание
        from handlers.post import start_create_post
        # Создаем виртуальный callback для переиспользования логики
        class FakeCallback:
            def __init__(self, msg):
                self.message = msg
                self.from_user = msg.from_user
                self.data = "create_post"
            async def answer(self, *args, **kwargs):
                pass
        
        fake_callback = FakeCallback(message)
        await start_create_post(fake_callback, state, bot)
    else:
        # Показываем главное меню
        role_text = "🚗 Водитель" if role == "driver" else "🚶 Пассажир"
        
        await message.answer(
            f"🎉 <b>Добро пожаловать!</b>\n\n"
            f"Роль: {role_text}\n"
            f"⭐ Рейтинг: 5.0\n\n"
            "Теперь вы можете создавать объявления\n"
            "и откликаться на чужие.",
            parse_mode="HTML",
            reply_markup=get_main_menu_keyboard(role, False)
        )

