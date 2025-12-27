# services/keys_generator.py - Генерация ключей из текста маршрута
# Критически важно для матчинга подписок

import re
from typing import List


def generate_keys(text: str) -> List[str]:
    """
    Генерирует ключи из текста маршрута.
    
    Правила:
    - Только слова (буквы кириллицы и латиницы)
    - Без цифр
    - Длина слова от 2 символов (чтобы учитывать короткие названия типа "Ош")
    - Регистр игнорируется (всё в lowercase)
    
    Примеры:
        "12 мкр дом 45" → ["мкр", "дом"]
        "Ош базар" → ["ош", "базар"]
        "Аламедин базар" → ["аламедин", "базар"]
        "ТЦ Дордой" → ["дордой"]
        "улица Токтогула 45а" → ["улица", "токтогула"]
    
    Args:
        text: Исходный текст маршрута
        
    Returns:
        Список уникальных ключей
    """
    if not text:
        return []
    
    # Убираем всё кроме букв (кириллица + латиница) и пробелов
    text_clean = re.sub(r'[^a-zA-Zа-яА-ЯёЁіІїЇєЄғҒқҚңҢөӨүҮһҺ\s]', ' ', text)
    
    # Разбиваем на слова и приводим к нижнему регистру
    words = text_clean.lower().split()
    
    # Фильтруем: только слова от 2 символов (чтобы учитывать короткие названия)
    keys = [word for word in words if len(word) >= 2]
    
    # Убираем дубликаты, сохраняя порядок
    seen = set()
    unique_keys = []
    for key in keys:
        if key not in seen:
            seen.add(key)
            unique_keys.append(key)
    
    return unique_keys


def keys_to_display(keys: List[str]) -> str:
    """
    Форматирует ключи для отображения пользователю.
    
    Args:
        keys: Список ключей
        
    Returns:
        Строка вида "аламедин, базар"
    """
    return ", ".join(keys) if keys else "—"


def validate_route_keys(keys_from: List[str], keys_to: List[str]) -> bool:
    """
    Проверяет, что ключи маршрута валидны.
    
    Args:
        keys_from: Ключи "откуда"
        keys_to: Ключи "куда"
        
    Returns:
        True если есть хотя бы по одному ключу
    """
    return len(keys_from) > 0 and len(keys_to) > 0

