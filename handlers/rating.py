# handlers/rating.py - Система рейтингов
# Оценка пользователей после поездки

from decimal import Decimal
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
import logging

from database.db import get_session
from database.models import User, Rating, Post
from keyboards import get_back_to_menu_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data.startswith("rate:"))
async def process_rating(callback: CallbackQuery):
    """Обработка оценки"""
    parts = callback.data.split(":")
    
    # Проверяем на пропуск
    if parts[1] == "skip":
        await callback.answer("Оценка пропущена")
        # Удаляем сообщение с запросом на оценку
        try:
            await callback.message.delete()
        except:
            pass
        return
    
    try:
        post_id = int(parts[1])
        to_user_id = int(parts[2])
        stars = int(parts[3])
    except (IndexError, ValueError):
        await callback.answer("Ошибка данных", show_alert=True)
        return
    
    if stars < 1 or stars > 5:
        await callback.answer("Неверная оценка", show_alert=True)
        return
    
    async with get_session() as session:
        # Получаем оценивающего
        from_user_query = select(User).where(User.telegram_id == callback.from_user.id)
        from_user_result = await session.execute(from_user_query)
        from_user = from_user_result.scalar_one_or_none()
        
        if not from_user:
            await callback.answer("Вы не зарегистрированы", show_alert=True)
            return
        
        # Получаем оцениваемого по telegram_id
        to_user_query = select(User).where(User.telegram_id == to_user_id)
        to_user_result = await session.execute(to_user_query)
        to_user = to_user_result.scalar_one_or_none()
        
        if not to_user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return
        
        # Проверяем, не оценивали ли уже
        existing_query = select(Rating).where(
            Rating.from_user_id == from_user.id,
            Rating.to_user_id == to_user.id,
            Rating.post_id == post_id
        )
        existing_result = await session.execute(existing_query)
        
        if existing_result.scalar_one_or_none():
            await callback.answer("Вы уже оценили эту поездку", show_alert=True)
            return
        
        # Создаём оценку
        rating = Rating(
            from_user_id=from_user.id,
            to_user_id=to_user.id,
            post_id=post_id,
            stars=stars
        )
        session.add(rating)
        
        # Обновляем средний рейтинг
        to_user.rating_count += 1
        
        # Пересчитываем средний рейтинг
        all_ratings_query = select(Rating).where(Rating.to_user_id == to_user.id)
        all_ratings_result = await session.execute(all_ratings_query)
        all_ratings = all_ratings_result.scalars().all()
        
        total_stars = sum(r.stars for r in all_ratings) + stars
        new_rating = Decimal(str(total_stars / (len(all_ratings) + 1))).quantize(Decimal("0.1"))
        to_user.rating = new_rating
        
        await session.commit()
        
        logger.info(f"Оценка: {from_user.id} → {to_user.id}: {stars}⭐")
    
    await callback.answer(f"✅ Оценка {stars}⭐ отправлена!")
    
    # Удаляем сообщение с запросом на оценку
    try:
        await callback.message.delete()
    except:
        # Если не удалось удалить, редактируем
        await callback.message.edit_text(
            f"✅ <b>Спасибо за оценку!</b>\n\n"
            f"Вы поставили: {'⭐' * stars}",
            parse_mode="HTML",
            reply_markup=get_back_to_menu_keyboard()
        )

