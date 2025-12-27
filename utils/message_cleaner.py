# utils/message_cleaner.py - Утилита для удаления сообщений
# Используется для поддержания чистоты чата во время диалогов

from typing import List
from aiogram import Bot
from aiogram.fsm.context import FSMContext
import logging

logger = logging.getLogger(__name__)


async def delete_messages(bot: Bot, chat_id: int, message_ids: List[int]) -> int:
    """
    Удаляет список сообщений из чата.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        message_ids: Список ID сообщений для удаления
    
    Returns:
        Количество успешно удалённых сообщений
    """
    deleted_count = 0
    
    for msg_id in message_ids:
        try:
            await bot.delete_message(chat_id, msg_id)
            deleted_count += 1
        except Exception as e:
            # Сообщение уже удалено или недоступно
            logger.debug(f"Не удалось удалить сообщение {msg_id}: {e}")
    
    return deleted_count


async def clean_chat(bot: Bot, chat_id: int, state: FSMContext) -> None:
    """
    Удаляет все сообщения, сохранённые в FSM state.
    После удаления очищает список в state.
    
    Args:
        bot: Экземпляр бота
        chat_id: ID чата
        state: FSM контекст с сохранёнными message_ids
    """
    data = await state.get_data()
    message_ids = data.get("messages_to_delete", [])
    
    if message_ids:
        await delete_messages(bot, chat_id, message_ids)
        await state.update_data(messages_to_delete=[])


async def add_message_to_delete(state: FSMContext, message_id: int) -> None:
    """
    Добавляет ID сообщения в список для последующего удаления.
    
    Args:
        state: FSM контекст
        message_id: ID сообщения для добавления
    """
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    messages.append(message_id)
    await state.update_data(messages_to_delete=messages)


async def add_messages_to_delete(state: FSMContext, message_ids: List[int]) -> None:
    """
    Добавляет несколько ID сообщений в список для удаления.
    
    Args:
        state: FSM контекст
        message_ids: Список ID сообщений
    """
    data = await state.get_data()
    messages = data.get("messages_to_delete", [])
    messages.extend(message_ids)
    await state.update_data(messages_to_delete=messages)

