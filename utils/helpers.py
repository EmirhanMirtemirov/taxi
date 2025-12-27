# utils/helpers.py - Вспомогательные функции

from datetime import datetime, timedelta
from typing import Optional
import pytz

from config import TIMEZONE


def format_time_remaining(expires_at: datetime) -> str:
    """
    Форматирует оставшееся время до истечения.
    
    Args:
        expires_at: Время истечения (UTC)
        
    Returns:
        Строка вида "45 мин" или "истекло"
    """
    now = datetime.utcnow()
    remaining = expires_at - now
    
    if remaining.total_seconds() <= 0:
        return "истекло"
    
    minutes = int(remaining.total_seconds() // 60)
    
    if minutes >= 60:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}ч {mins}мин"
    
    return f"{minutes} мин"


def format_rating(rating: float, count: int) -> str:
    """
    Форматирует рейтинг для отображения.
    
    Args:
        rating: Средний рейтинг
        count: Количество оценок
        
    Returns:
        Строка вида "4.5 (23 оценки)"
    """
    rating_str = f"{float(rating):.1f}"
    
    if count == 0:
        return f"{rating_str} (нет оценок)"
    
    # Склонение слова "оценка"
    if count % 10 == 1 and count % 100 != 11:
        word = "оценка"
    elif 2 <= count % 10 <= 4 and (count % 100 < 10 or count % 100 >= 20):
        word = "оценки"
    else:
        word = "оценок"
    
    return f"{rating_str} ({count} {word})"


def truncate_text(text: str, max_length: int = 20) -> str:
    """
    Обрезает текст до указанной длины.
    
    Args:
        text: Исходный текст
        max_length: Максимальная длина
        
    Returns:
        Обрезанный текст с "..." если нужно
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def format_local_time(utc_datetime: datetime, format_str: str = "%H:%M") -> str:
    """
    Конвертирует UTC время в локальный часовой пояс и форматирует.
    
    Args:
        utc_datetime: Время в UTC (может быть наивным datetime)
        format_str: Формат строки (по умолчанию "%H:%M")
        
    Returns:
        Отформатированная строка времени в локальном часовом поясе
    """
    local_tz = pytz.timezone(TIMEZONE)
    
    # Если datetime наивное (без timezone), считаем его UTC
    if utc_datetime.tzinfo is None:
        utc_datetime = pytz.utc.localize(utc_datetime)
    
    local_datetime = utc_datetime.astimezone(local_tz)
    return local_datetime.strftime(format_str)

