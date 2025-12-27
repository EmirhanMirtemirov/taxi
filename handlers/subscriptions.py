# handlers/subscriptions.py - Управление подписками на маршруты
# Добавление, просмотр и удаление подписок

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
import logging

from states import Subscriptions
from database.db import get_session
from database.models import User, Subscription
from services.keys_generator import generate_keys, keys_to_display
from utils.message_cleaner import add_message_to_delete, clean_chat
from keyboards import (
    get_subscriptions_keyboard,
    get_subscriptions_list_keyboard,
    get_subscription_confirm_keyboard,
    get_cancel_keyboard,
    get_back_cancel_keyboard,
    get_remove_keyboard,
    get_back_to_menu_keyboard
)

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "subscriptions")
async def show_subscriptions(callback: CallbackQuery, state: FSMContext):
    """Показать список подписок"""
    await callback.answer()
    await state.clear()
    
    async with get_session() as session:
        # Получаем пользователя
        user_query = select(User).where(User.telegram_id == callback.from_user.id)
        user_result = await session.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            await callback.message.edit_text("❌ Вы не зарегистрированы. /start")
            return
        
        # Получаем подписки
        subs_query = select(Subscription).where(Subscription.user_id == user.id)
        subs_result = await session.execute(subs_query)
        subscriptions = subs_result.scalars().all()
        
        if not subscriptions:
            text = (
                "🔔 <b>Ваши подписки на маршруты</b>\n\n"
                "У вас пока нет подписок.\n\n"
                "Подписка позволяет получать уведомления,\n"
                "когда появляется объявление по вашему маршруту."
            )
        else:
            subs_list = []
            for i, sub in enumerate(subscriptions, 1):
                from_text = sub.from_text or keys_to_display(sub.keys_from)
                to_text = sub.to_text or keys_to_display(sub.keys_to)
                subs_list.append(f"{i}. {from_text} → {to_text}")
            
            text = (
                "🔔 <b>Ваши подписки на маршруты:</b>\n\n" +
                "\n".join(subs_list)
            )
        
        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=get_subscriptions_keyboard()
        )


@router.callback_query(F.data == "sub:add")
async def start_add_subscription(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Начало добавления подписки"""
    await callback.answer()
    
    # Очищаем предыдущие сообщения перед началом нового диалога
    await clean_chat(bot, callback.from_user.id, state)
    await state.update_data(messages_to_delete=[])
    
    # Получаем user_id
    async with get_session() as session:
        user_query = select(User).where(User.telegram_id == callback.from_user.id)
        user_result = await session.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            return
        
        await state.update_data(user_id=user.id)
    
    try:
        await callback.message.delete()
    except:
        pass
    
    msg = await callback.message.answer(
        "📍 <b>Добавление подписки</b>\n\n"
        "Откуда вы обычно едете?\n"
        "<i>(например: Аламедин)</i>",
        parse_mode="HTML",
        reply_markup=get_cancel_keyboard()
    )
    await add_message_to_delete(state, msg.message_id)
    
    await state.set_state(Subscriptions.adding_from)


@router.message(Subscriptions.adding_from, F.text)
async def process_sub_from(message: Message, state: FSMContext, bot: Bot):
    """Обработка 'откуда' для подписки"""
    if message.text == "❌ Отмена":
        await clean_chat(bot, message.chat.id, state)
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_remove_keyboard())
        await message.answer("Что дальше?", reply_markup=get_back_to_menu_keyboard())
        return
    
    await add_message_to_delete(state, message.message_id)
    
    await state.update_data(
        from_text=message.text.strip(),
        keys_from=generate_keys(message.text.strip())
    )
    
    msg = await message.answer(
        "📍 <b>Добавление подписки</b>\n\n"
        "Куда вы обычно едете?\n"
        "<i>(например: Дордой)</i>",
        parse_mode="HTML",
        reply_markup=get_back_cancel_keyboard()
    )
    await add_message_to_delete(state, msg.message_id)
    
    await state.set_state(Subscriptions.adding_to)


@router.message(Subscriptions.adding_to, F.text)
async def process_sub_to(message: Message, state: FSMContext, bot: Bot):
    """Обработка 'куда' для подписки"""
    if message.text == "❌ Отмена":
        await clean_chat(bot, message.chat.id, state)
        await state.clear()
        await message.answer("Отменено.", reply_markup=get_remove_keyboard())
        await message.answer("Что дальше?", reply_markup=get_back_to_menu_keyboard())
        return
    
    if message.text == "◀️ Назад":
        await add_message_to_delete(state, message.message_id)
        msg = await message.answer(
            "📍 <b>Добавление подписки</b>\n\n"
            "Откуда вы обычно едете?",
            parse_mode="HTML",
            reply_markup=get_cancel_keyboard()
        )
        await add_message_to_delete(state, msg.message_id)
        await state.set_state(Subscriptions.adding_from)
        return
    
    await add_message_to_delete(state, message.message_id)
    
    await state.update_data(
        to_text=message.text.strip(),
        keys_to=generate_keys(message.text.strip())
    )
    
    # Показываем подтверждение
    data = await state.get_data()
    
    msg1 = await message.answer(
        f"📋 <b>Проверьте подписку:</b>\n\n"
        f"📍 Откуда: {data['from_text']}\n"
        f"📍 Куда: {data['to_text']}\n\n"
        f"🔑 Ключи: {keys_to_display(data['keys_from'])} → {keys_to_display(data['keys_to'])}",
        parse_mode="HTML",
        reply_markup=get_remove_keyboard()
    )
    
    msg2 = await message.answer(
        "Подписаться?",
        reply_markup=get_subscription_confirm_keyboard()
    )
    
    await add_message_to_delete(state, msg1.message_id)
    await add_message_to_delete(state, msg2.message_id)
    
    await state.set_state(Subscriptions.confirming_add)


@router.callback_query(Subscriptions.confirming_add, F.data == "sub:confirm")
async def confirm_subscription(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждение подписки"""
    await callback.answer()
    
    data = await state.get_data()
    
    async with get_session() as session:
        # Проверяем, не существует ли уже такая подписка
        existing_sub_query = select(Subscription).where(
            Subscription.user_id == data["user_id"],
            Subscription.keys_from == data["keys_from"],
            Subscription.keys_to == data["keys_to"]
        )
        existing_sub_result = await session.execute(existing_sub_query)
        existing_sub = existing_sub_result.scalar_one_or_none()
        
        if existing_sub:
            # Подписка уже существует
            await clean_chat(bot, callback.from_user.id, state)
            try:
                await callback.message.edit_text(
                    "❌ Такая подписка уже существует.",
                    reply_markup=get_back_to_menu_keyboard()
                )
            except Exception:
                await callback.message.answer(
                    "❌ Такая подписка уже существует.",
                    reply_markup=get_back_to_menu_keyboard()
                )
        else:
            # Создаем новую подписку
            subscription = Subscription(
                user_id=data["user_id"],
                keys_from=data["keys_from"],
                keys_to=data["keys_to"],
                from_text=data["from_text"],
                to_text=data["to_text"]
            )
            
            try:
                session.add(subscription)
                await session.commit()
                
                # Очищаем все временные сообщения перед завершением диалога
                await clean_chat(bot, callback.from_user.id, state)
                
                # После clean_chat сообщение удалено, используем answer вместо edit_text
                try:
                    await callback.message.edit_text(
                        "✅ <b>Подписка создана!</b>\n\n"
                        "Вы получите уведомление, когда появится\n"
                        "объявление по этому маршруту.",
                        parse_mode="HTML",
                        reply_markup=get_back_to_menu_keyboard()
                    )
                except Exception:
                    # Если сообщение уже удалено, отправляем новое
                    await callback.message.answer(
                        "✅ <b>Подписка создана!</b>\n\n"
                        "Вы получите уведомление, когда появится\n"
                        "объявление по этому маршруту.",
                        parse_mode="HTML",
                        reply_markup=get_back_to_menu_keyboard()
                    )
                
            except IntegrityError as e:
                # Дублирующаяся подписка (на случай race condition)
                await session.rollback()  # Важно: откатываем транзакцию
                logger.warning(f"Попытка создать дублирующуюся подписку: {e}")
                await clean_chat(bot, callback.from_user.id, state)
                try:
                    await callback.message.edit_text(
                        "❌ Такая подписка уже существует.",
                        reply_markup=get_back_to_menu_keyboard()
                    )
                except Exception:
                    await callback.message.answer(
                        "❌ Такая подписка уже существует.",
                        reply_markup=get_back_to_menu_keyboard()
                    )
            except Exception as e:
                # Другие ошибки
                await session.rollback()  # Важно: откатываем транзакцию
                logger.error(f"Ошибка создания подписки: {e}", exc_info=True)
                await clean_chat(bot, callback.from_user.id, state)
                try:
                    await callback.message.edit_text(
                        "❌ Произошла ошибка при создании подписки.\nПопробуйте позже.",
                        reply_markup=get_back_to_menu_keyboard()
                    )
                except Exception:
                    await callback.message.answer(
                        "❌ Произошла ошибка при создании подписки.\nПопробуйте позже.",
                        reply_markup=get_back_to_menu_keyboard()
                    )
    
    await state.clear()


@router.callback_query(F.data == "sub:delete")
async def start_delete_subscription(callback: CallbackQuery, state: FSMContext):
    """Начало удаления подписки"""
    await callback.answer()
    
    async with get_session() as session:
        user_query = select(User).where(User.telegram_id == callback.from_user.id)
        user_result = await session.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            return
        
        subs_query = select(Subscription).where(Subscription.user_id == user.id)
        subs_result = await session.execute(subs_query)
        subscriptions = list(subs_result.scalars().all())
        
        if not subscriptions:
            await callback.answer("У вас нет подписок", show_alert=True)
            return
        
        await callback.message.edit_text(
            "🗑 <b>Выберите подписку для удаления:</b>",
            parse_mode="HTML",
            reply_markup=get_subscriptions_list_keyboard(subscriptions, for_delete=True)
        )


@router.callback_query(F.data.startswith("sub_delete:"))
async def delete_subscription(callback: CallbackQuery):
    """Удаление подписки"""
    sub_id = int(callback.data.split(":")[1])
    
    async with get_session() as session:
        await session.execute(
            delete(Subscription).where(Subscription.id == sub_id)
        )
        await session.commit()
    
    await callback.answer("✅ Подписка удалена")
    
    # Возвращаемся к списку
    await show_subscriptions(callback, FSMContext)

