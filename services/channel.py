# services/channel.py - Публикация в Telegram канал
# Форматирование и управление сообщениями в канале

from datetime import datetime
from typing import Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

from config import CHANNEL_ID
from database.models import Post, User
from utils.helpers import format_local_time

logger = logging.getLogger(__name__)


def format_post_for_channel(post: Post, author: User) -> str:
    """
    Форматирует объявление для публикации в канал.
    
    Args:
        post: Объявление
        author: Автор объявления
        
    Returns:
        Отформатированный текст
    """
    # Определяем тип объявления
    if post.role == "driver":
        role_emoji = "🚗"
        role_text = "Водитель"
        seats_line = f"Мест: {post.seats}\n" if post.seats else ""
    else:
        role_emoji = "🚶"
        role_text = "Пассажир"
        seats_line = ""
    
    # Форматируем время отправления
    departure_time = post.departure_time or "Не указано"
    
    text = (
        f"{role_emoji} КТО: {role_text}\n"
        f"📍 Откуда: {post.from_place}\n"
        f"📍 Куда: {post.to_place}\n"
        f"⏰ Время: {departure_time}\n"
    )
    
    # Добавляем количество мест только для водителей
    if seats_line:
        text += seats_line
    
    text += f"💰 Цена: {post.price} сом"
    
    return text


def get_channel_keyboard(bot_username: str, post_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура под объявлением в канале.
    
    Args:
        bot_username: Username бота
        post_id: ID объявления
        
    Returns:
        Inline клавиатура
    """
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📱 Связаться",
            url=f"https://t.me/{bot_username}?start=post_{post_id}"
        )]
    ])


def format_expired_post(post: Post) -> str:
    """
    Форматирует истёкшее объявление.
    
    Args:
        post: Объявление
        
    Returns:
        Текст с пометкой об истечении
    """
    role_emoji = "🚗" if post.role == "driver" else "🚶"
    role_text = "ВОДИТЕЛЬ" if post.role == "driver" else "ПАССАЖИР"
    
    text = (
        f"⏰ <b>ИСТЕКЛО</b>\n\n"
        f"{role_emoji} <s>{role_text}</s>\n\n"
        f"📍 <s>{post.from_place} → {post.to_place}</s>\n"
    )
    
    return text


async def publish_to_channel(
    bot: Bot,
    post: Post,
    author: User
) -> Optional[int]:
    """
    Публикует объявление в канал.
    Для водителей с фото отправляет фото, для остальных - текстовое сообщение.
    
    Args:
        bot: Экземпляр бота
        post: Объявление
        author: Автор
        
    Returns:
        ID сообщения в канале или None при ошибке
    """
    try:
        bot_info = await bot.get_me()
        text = format_post_for_channel(post, author)
        keyboard = get_channel_keyboard(bot_info.username, post.id)
        
        # Если это водитель и у него есть фото автомобиля - отправляем фото
        if post.role == "driver" and author.car_photo_file_id:
            message = await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=author.car_photo_file_id,
                caption=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_notification=True  # Отправляем в канал без звука
            )
        else:
            # Обычное текстовое сообщение
            message = await bot.send_message(
                chat_id=CHANNEL_ID,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_notification=True  # Отправляем в канал без звука
            )
        
        logger.info(f"Объявление {post.id} опубликовано в канал, message_id={message.message_id}")
        return message.message_id
        
    except Exception as e:
        logger.error(f"Ошибка публикации в канал: {e}")
        return None


async def update_channel_message(
    bot: Bot,
    message_id: int,
    text: str,
    keyboard: Optional[InlineKeyboardMarkup] = None
) -> bool:
    """
    Обновляет сообщение в канале.
    
    Args:
        bot: Экземпляр бота
        message_id: ID сообщения
        text: Новый текст
        keyboard: Новая клавиатура (опционально)
        
    Returns:
        True при успехе
    """
    try:
        await bot.edit_message_text(
            chat_id=CHANNEL_ID,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return True
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение {message_id}: {e}")
        return False


async def delete_channel_message(bot: Bot, message_id: int) -> bool:
    """
    Удаляет сообщение из канала.
    
    Args:
        bot: Экземпляр бота
        message_id: ID сообщения
        
    Returns:
        True при успехе
    """
    try:
        await bot.delete_message(chat_id=CHANNEL_ID, message_id=message_id)
        logger.info(f"Сообщение {message_id} удалено из канала")
        return True
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {message_id}: {e}")
        return False


async def mark_post_as_expired(bot: Bot, post: Post) -> None:
    """
    Помечает объявление как истёкшее в канале.
    
    Args:
        bot: Экземпляр бота
        post: Объявление
    """
    if post.channel_message_id:
        expired_text = format_expired_post(post)
        await update_channel_message(
            bot,
            post.channel_message_id,
            expired_text,
            keyboard=None  # Убираем кнопку
        )


async def send_pinned_menu_message(bot: Bot) -> Optional[int]:
    """
    Отправляет закрепленное сообщение с кнопкой "Создать объявление" в канал.
    Если сообщение уже существует - не отправляет новое.
    
    Args:
        bot: Экземпляр бота
        
    Returns:
        ID сообщения или None при ошибке
    """
    try:
        # Проверяем, есть ли уже закрепленное сообщение в канале
        try:
            chat = await bot.get_chat(CHANNEL_ID)
            if hasattr(chat, 'pinned_message') and chat.pinned_message:
                # Проверяем, что это наше сообщение (с кнопкой "Создать объявление")
                pinned_msg = chat.pinned_message
                if pinned_msg.reply_markup and pinned_msg.reply_markup.inline_keyboard:
                    # Проверяем текст кнопки
                    for row in pinned_msg.reply_markup.inline_keyboard:
                        for button in row:
                            if button.text in ["Создать объявление", "Создать заказ"]:
                                logger.info(f"Закрепленное сообщение уже существует в канале (msg_id={pinned_msg.message_id})")
                                return pinned_msg.message_id
        except Exception as e:
            logger.debug(f"Не удалось проверить закрепленное сообщение: {e}")
        
        # Если закрепленного сообщения нет или это не наше - отправляем новое
        bot_info = await bot.get_me()
        bot_username = bot_info.username
        
        text = "Создать заказ о поездке через бот"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Создать заказ",
                url=f"https://t.me/{bot_username}?start=create_post"
            )]
        ])
        
        message = await bot.send_message(
            chat_id=CHANNEL_ID,
            text=text,
            parse_mode="HTML",
            reply_markup=keyboard,
            disable_notification=True
        )
        
        # Закрепляем сообщение
        try:
            await bot.pin_chat_message(
                chat_id=CHANNEL_ID,
                message_id=message.message_id,
                disable_notification=True
            )
            logger.info(f"Закрепленное сообщение с кнопкой отправлено в канал, message_id={message.message_id}")
        except Exception as e:
            logger.warning(f"Не удалось закрепить сообщение: {e}")
        
        return message.message_id
        
    except Exception as e:
        logger.error(f"Ошибка отправки закрепленного сообщения в канал: {e}")
        return None

