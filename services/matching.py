# services/matching.py - Логика матчинга маршрутов
# Находит совпадения между объявлениями и подписками

from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from database.models import Subscription, User, Post, NotificationLog

logger = logging.getLogger(__name__)


async def find_matching_subscriptions(
    session: AsyncSession, 
    post: Post
) -> List[int]:
    """
    Находит пользователей, чьи подписки совпадают с объявлением.
    
    ПРАВИЛО СОВПАДЕНИЯ (СТРОГО):
    Совпадение засчитывается ТОЛЬКО если:
    1. ВСЕ ключи из keys_from подписки присутствуют в keys_from объявления
    2. И ВСЕ ключи из keys_to подписки присутствуют в keys_to объявления
    3. ОБА условия должны выполняться одновременно!
    
    Это предотвращает ложные совпадения из-за общих слов типа "базар".
    
    Примеры:
    - Подписка ["базар"] и объявление ["дордой", "базар"] → совпадает (все ключи подписки есть)
    - Подписка ["ош", "базар"] и объявление ["дордой", "базар"] → НЕ совпадает (нет "ош")
    - Подписка ["ош", "базар"] и объявление ["ош", "базар", "центр"] → совпадает (все ключи есть)
    
    Args:
        session: Сессия БД
        post: Объявление для проверки
        
    Returns:
        Список user_id пользователей с совпавшими подписками
    """
    # Получаем все подписки
    subscriptions_query = select(Subscription).where(
            Subscription.user_id != post.author_id
        )
    result = await session.execute(subscriptions_query)
    subscriptions = result.scalars().all()
    
    matching_user_ids = []
    post_keys_from_set = set(post.keys_from)
    post_keys_to_set = set(post.keys_to)
    
    for sub in subscriptions:
        sub_keys_from = set(sub.keys_from)
        sub_keys_to = set(sub.keys_to)
        
        # Подсчитываем совпадающие ключи
        from_intersection = sub_keys_from & post_keys_from_set
        to_intersection = sub_keys_to & post_keys_to_set
        
        # Требуем совпадение ВСЕХ ключей подписки
        # Это предотвращает ложные совпадения из-за общих слов
        from_match = sub_keys_from.issubset(post_keys_from_set)
        to_match = sub_keys_to.issubset(post_keys_to_set)
        
        # Детальное логирование для отладки
        logger.debug(
            f"Проверка подписки {sub.id} (user_id={sub.user_id}):\n"
            f"  Подписка keys_from: {list(sub_keys_from)}, keys_to: {list(sub_keys_to)}\n"
            f"  Объявление keys_from: {list(post_keys_from_set)}, keys_to: {list(post_keys_to_set)}\n"
            f"  Пересечение from: {list(from_intersection)} ({len(from_intersection)}), to: {list(to_intersection)} ({len(to_intersection)})\n"
            f"  Требуется: ВСЕ ключи подписки должны быть в объявлении\n"
            f"  Результат: from_match={from_match}, to_match={to_match}"
        )
        
        if from_match and to_match:
            logger.info(f"✅ Подписка {sub.id} совпадает с постом {post.id}")
            matching_user_ids.append(sub.user_id)
        else:
            logger.debug(f"❌ Подписка {sub.id} НЕ совпадает с постом {post.id}")
    
    logger.info(f"Найдено {len(matching_user_ids)} совпадений для поста {post.id}")
    
    return matching_user_ids


async def check_subscription_match(
    keys_from_sub: List[str],
    keys_to_sub: List[str],
    keys_from_post: List[str],
    keys_to_post: List[str]
) -> bool:
    """
    Проверяет совпадение подписки с объявлением.
    
    Правило: ВСЕ ключи подписки должны присутствовать в объявлении.
    Это предотвращает ложные совпадения из-за общих слов.
    
    Args:
        keys_from_sub: Ключи "откуда" из подписки
        keys_to_sub: Ключи "куда" из подписки
        keys_from_post: Ключи "откуда" из объявления
        keys_to_post: Ключи "куда" из объявления
        
    Returns:
        True если ВСЕ ключи подписки присутствуют в объявлении
    """
    # Проверяем, что ВСЕ ключи подписки есть в объявлении
    from_match = set(keys_from_sub).issubset(set(keys_from_post))
    to_match = set(keys_to_sub).issubset(set(keys_to_post))
    
    # Совпадение только если ОБА условия выполнены
    return from_match and to_match


async def get_users_to_notify(
    session: AsyncSession,
    post: Post,
    matching_user_ids: List[int]
) -> List[User]:
    """
    Получает пользователей для уведомления, исключая тех, 
    кому уже отправлялось уведомление об этом объявлении.
    
    Args:
        session: Сессия БД
        post: Объявление
        matching_user_ids: Список ID пользователей с совпадениями
        
    Returns:
        Список пользователей для уведомления
    """
    if not matching_user_ids:
        return []
    
    # Получаем ID тех, кому уже отправлено
    already_notified_query = select(NotificationLog.recipient_id).where(
        NotificationLog.post_id == post.id
    )
    result = await session.execute(already_notified_query)
    already_notified = {row[0] for row in result.fetchall()}
    
    # Фильтруем
    to_notify_ids = [uid for uid in matching_user_ids if uid not in already_notified]
    
    if not to_notify_ids:
        return []
    
    # Получаем данные пользователей
    users_query = select(User).where(User.id.in_(to_notify_ids))
    result = await session.execute(users_query)
    users = result.scalars().all()
    
    return list(users)


async def find_matching_posts(
    session: AsyncSession,
    post: Post
) -> List[Post]:
    """
    Находит активные объявления противоположной роли с совпадающим маршрутом.
    
    Правило совпадения (СТРОГО):
    - Если post.role == "driver" → ищет объявления с role == "passenger"
    - Если post.role == "passenger" → ищет объявления с role == "driver"
    - Маршрут должен совпадать В ТОМ ЖЕ НАПРАВЛЕНИИ:
      * ВСЕ ключи keys_from кандидата должны присутствовать в keys_from текущего поста
      * И ВСЕ ключи keys_to кандидата должны присутствовать в keys_to текущего поста
      * ИЛИ наоборот (если текущий пост более общий)
    - Это предотвращает ложные совпадения из-за общих слов типа "базар"
    - Это предотвращает совпадение обратных маршрутов
    
    Примеры:
    - Пост ["ош", "базар"] → ["аламедин", "базар"] совпадает с ["ош", "базар"] → ["аламедин", "базар"]
    - Пост ["ош", "базар"] → ["аламедин", "базар"] НЕ совпадает с ["аламедин", "базар"] → ["ош", "базар"] (обратное направление)
    - Пост ["ош", "базар"] → ["аламедин", "базар"] НЕ совпадает с ["дордой", "базар"] → ["мадина"] (нет "ош" и "аламедин")
    
    Args:
        session: Сессия БД
        post: Объявление для проверки
        
    Returns:
        Список совпадающих объявлений
    """
    # Определяем противоположную роль
    opposite_role = "passenger" if post.role == "driver" else "driver"
    
    # Получаем все активные объявления противоположной роли
    query = select(Post).where(
        and_(
            Post.role == opposite_role,
            Post.status == "active",
            Post.author_id != post.author_id  # Исключаем автора
        )
    )
    
    result = await session.execute(query)
    all_posts = result.scalars().all()
    
    # Проверяем совпадение маршрутов строго (с учетом направления)
    matching_posts = []
    post_keys_from_set = set(post.keys_from)
    post_keys_to_set = set(post.keys_to)
    
    for candidate_post in all_posts:
        candidate_keys_from_set = set(candidate_post.keys_from)
        candidate_keys_to_set = set(candidate_post.keys_to)
        
        # Проверяем: ВСЕ ключи должны совпадать В ТОМ ЖЕ НАПРАВЛЕНИИ
        # Вариант 1: все ключи текущего поста в кандидате (текущий более общий)
        match_1 = (post_keys_from_set.issubset(candidate_keys_from_set) and 
                  post_keys_to_set.issubset(candidate_keys_to_set))
        
        # Вариант 2: все ключи кандидата в текущем посте (кандидат более общий)
        match_2 = (candidate_keys_from_set.issubset(post_keys_from_set) and 
                  candidate_keys_to_set.issubset(post_keys_to_set))
        
        # Совпадение только если выполняется хотя бы один вариант
        if match_1 or match_2:
            matching_posts.append(candidate_post)
            logger.debug(
                f"✅ Пост {candidate_post.id} совпадает с постом {post.id}:\n"
                f"  Пост {post.id}: {list(post_keys_from_set)} → {list(post_keys_to_set)}\n"
                f"  Пост {candidate_post.id}: {list(candidate_keys_from_set)} → {list(candidate_keys_to_set)}"
            )
        else:
            logger.debug(
                f"❌ Пост {candidate_post.id} НЕ совпадает с постом {post.id}:\n"
                f"  Пост {post.id}: {list(post_keys_from_set)} → {list(post_keys_to_set)}\n"
                f"  Пост {candidate_post.id}: {list(candidate_keys_from_set)} → {list(candidate_keys_to_set)}"
            )
    
    logger.info(f"Найдено {len(matching_posts)} совпадающих объявлений для поста {post.id} (роль: {post.role})")
    
    return matching_posts


async def log_notification(
    session: AsyncSession,
    post_id: int,
    recipient_id: int,
    notification_message_id: int = None,
    recipient_telegram_id: int = None
) -> None:
    """
    Записывает в лог отправленное уведомление.
    
    Args:
        session: Сессия БД
        post_id: ID объявления
        recipient_id: ID получателя (в БД)
        notification_message_id: ID сообщения уведомления в Telegram
        recipient_telegram_id: Telegram ID получателя
    """
    log_entry = NotificationLog(
        post_id=post_id,
        recipient_id=recipient_id,
        notification_message_id=notification_message_id,
        recipient_telegram_id=recipient_telegram_id
    )
    session.add(log_entry)
    await session.commit()

