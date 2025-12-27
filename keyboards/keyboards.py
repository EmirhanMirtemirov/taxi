# keyboards/keyboards.py - Все клавиатуры бота
# Обновлённые клавиатуры для нового флоу

from typing import List, Optional
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton
)


# ==================== СОГЛАСИЕ С ПРАВИЛАМИ ====================

def get_agreement_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура согласия с правилами"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ СОГЛАСЕН", callback_data="agreement:accept")],
        [InlineKeyboardButton(text="❌ ВЫЙТИ", callback_data="agreement:decline")]
    ])


# ==================== ВЫБОР РОЛИ ====================

def get_role_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора роли при регистрации"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚗 Я водитель", callback_data="role:driver")],
        [InlineKeyboardButton(text="🚶 Я пассажир", callback_data="role:passenger")]
    ])


# ==================== РЕГИСТРАЦИЯ ====================

def get_phone_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура для запроса телефона"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Отправить мой контакт", request_contact=True)],
            [KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


# ==================== ГЛАВНОЕ МЕНЮ ====================

def get_main_menu_keyboard(role: str, has_active_post: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура главного меню
    
    Args:
        role: Роль пользователя ('driver' или 'passenger')
        has_active_post: Есть ли активное объявление
    """
    buttons = [
        [InlineKeyboardButton(text="📝 Создать объявление", callback_data="create_post")]
    ]
    
    if has_active_post:
        buttons.append([
            InlineKeyboardButton(text="📋 Мои объявления", callback_data="my_posts")
        ])
    
    buttons.extend([
        [InlineKeyboardButton(text="🔔 Мои подписки", callback_data="subscriptions")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==================== СОЗДАНИЕ ОБЪЯВЛЕНИЯ ====================

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура только с кнопкой отмены"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True
    )


def get_back_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура с кнопками Назад и Отмена"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="◀️ Назад"), KeyboardButton(text="❌ Отмена")]
        ],
        resize_keyboard=True
    )


def get_seats_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура выбора количества мест (для водителей)"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data="seats:1"),
            InlineKeyboardButton(text="2", callback_data="seats:2"),
            InlineKeyboardButton(text="3", callback_data="seats:3"),
            InlineKeyboardButton(text="4", callback_data="seats:4")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="seats:back")]
    ])


def get_post_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения объявления"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опубликовать", callback_data="post:publish")],
        [InlineKeyboardButton(text="🔔 Подписаться на маршрут", callback_data="post:subscribe")],
        [InlineKeyboardButton(text="✏️ Изменить", callback_data="post:edit")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="post:cancel")]
    ])


def get_after_publish_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура после публикации"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏸ Приостановить", callback_data="post:pause")],
        [InlineKeyboardButton(text="❌ Удалить", callback_data="post:delete")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
    ])


# ==================== МОИ ОБЪЯВЛЕНИЯ ====================

def get_post_actions_keyboard(post_id: int, status: str) -> InlineKeyboardMarkup:
    """
    Клавиатура действий с объявлением
    
    Args:
        post_id: ID объявления
        status: Статус объявления
    """
    buttons = []
    
    if status == "active":
        buttons.append([InlineKeyboardButton(
            text="⏸ Приостановить",
            callback_data=f"post_action:pause:{post_id}"
        )])
    elif status == "paused":
        buttons.append([InlineKeyboardButton(
            text="▶️ Возобновить",
            callback_data=f"post_action:resume:{post_id}"
        )])
    
    if status in ["active", "paused"]:
        buttons.append([InlineKeyboardButton(
            text="🔄 Продлить +60 мин",
            callback_data=f"post_action:extend:{post_id}"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="❌ Удалить",
        callback_data=f"post_action:delete:{post_id}"
    )])
    
    buttons.append([InlineKeyboardButton(
        text="◀️ Назад",
        callback_data="my_posts"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_posts_list_keyboard(posts: list) -> InlineKeyboardMarkup:
    """Клавиатура списка объявлений"""
    buttons = []
    
    for i, post in enumerate(posts, 1):
        status_emoji = "🟢" if post.status == "active" else "⏸"
        text = f"{status_emoji} {post.from_place[:15]}... → {post.to_place[:15]}..."
        buttons.append([InlineKeyboardButton(
            text=text,
            callback_data=f"view_post:{post.id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==================== ПОДПИСКИ ====================

def get_subscriptions_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура управления подписками"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить подписку", callback_data="sub:add")],
        [InlineKeyboardButton(text="🗑 Удалить подписку", callback_data="sub:delete")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
    ])


def get_subscriptions_list_keyboard(subscriptions: list, for_delete: bool = False) -> InlineKeyboardMarkup:
    """
    Клавиатура списка подписок
    
    Args:
        subscriptions: Список подписок
        for_delete: Если True - для удаления
    """
    buttons = []
    
    for i, sub in enumerate(subscriptions, 1):
        from_text = ", ".join(sub.keys_from[:2])
        to_text = ", ".join(sub.keys_to[:2])
        text = f"{i}. {from_text} → {to_text}"
        
        if for_delete:
            buttons.append([InlineKeyboardButton(
                text=f"🗑 {text}",
                callback_data=f"sub_delete:{sub.id}"
            )])
        else:
            buttons.append([InlineKeyboardButton(
                text=text,
                callback_data=f"sub_view:{sub.id}"
            )])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="subscriptions")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_subscription_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения подписки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подписаться", callback_data="sub:confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="subscriptions")]
    ])


# ==================== ПРОФИЛЬ ====================

def get_profile_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура профиля"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Изменить телефон", callback_data="profile:phone")],
        [InlineKeyboardButton(text="🔄 Сменить роль", callback_data="profile:role")],
        [InlineKeyboardButton(text="🗑 Удалить профиль", callback_data="profile:delete")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
    ])


def get_role_change_keyboard(current_role: str) -> InlineKeyboardMarkup:
    """Клавиатура смены роли"""
    new_role = "passenger" if current_role == "driver" else "driver"
    new_role_text = "🚶 Пассажир" if new_role == "passenger" else "🚗 Водитель"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"Сменить на: {new_role_text}",
            callback_data=f"switch_role:{new_role}"
        )],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="profile")]
    ])


def get_delete_profile_confirm_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура подтверждения удаления профиля"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data="profile:delete_confirm")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="profile")]
    ])


# ==================== КОНТАКТ (ТОЛЬКО ПРИ СОВПАДЕНИИ) ====================

def get_contact_keyboard(phone: str, telegram_id: int) -> InlineKeyboardMarkup:
    """
    Клавиатура с контактами (показывается ТОЛЬКО при совпадении маршрутов)
    
    Args:
        phone: Номер телефона (может быть с +)
        telegram_id: Telegram ID пользователя
    """
    # Telegram не всегда правильно обрабатывает tel: ссылки с международными номерами
    # Поэтому используем только кнопку "Написать в Telegram"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Написать в Telegram", url=f"tg://user?id={telegram_id}")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
    ])


# ==================== РЕЙТИНГ ====================

def get_rating_keyboard(post_id: int, to_user_id: int) -> InlineKeyboardMarkup:
    """Клавиатура оценки поездки"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⭐ 1", callback_data=f"rate:{post_id}:{to_user_id}:1"),
            InlineKeyboardButton(text="⭐ 2", callback_data=f"rate:{post_id}:{to_user_id}:2"),
            InlineKeyboardButton(text="⭐ 3", callback_data=f"rate:{post_id}:{to_user_id}:3"),
            InlineKeyboardButton(text="⭐ 4", callback_data=f"rate:{post_id}:{to_user_id}:4"),
            InlineKeyboardButton(text="⭐ 5", callback_data=f"rate:{post_id}:{to_user_id}:5"),
        ],
        [InlineKeyboardButton(text="⏭ Пропустить", callback_data="rate:skip")]
    ])


# ==================== ПОМОЩЬ ====================

def get_help_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура помощи"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
    ])


# ==================== ИСТЕКШЕЕ ОБЪЯВЛЕНИЕ ====================

def get_expired_post_keyboard(post_id: int) -> InlineKeyboardMarkup:
    """Клавиатура для истёкшего объявления"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Создать такое же", callback_data=f"recreate:{post_id}")],
        [InlineKeyboardButton(text="📝 Новое объявление", callback_data="create_post")],
        [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
    ])


# ==================== СУЩЕСТВУЮЩЕЕ ОБЪЯВЛЕНИЕ ====================

def get_existing_post_keyboard(post_id: int, status: str) -> InlineKeyboardMarkup:
    """
    Клавиатура для случая, когда у пользователя уже есть активное объявление
    
    Args:
        post_id: ID объявления
        status: Статус объявления (active/paused)
    """
    buttons = []
    
    if status == "active":
        buttons.append([InlineKeyboardButton(
            text="⏸ Приостановить",
            callback_data=f"post_action:pause:{post_id}"
        )])
    elif status == "paused":
        buttons.append([InlineKeyboardButton(
            text="▶️ Возобновить",
            callback_data=f"post_action:resume:{post_id}"
        )])
    
    buttons.append([InlineKeyboardButton(
        text="❌ Удалить объявление",
        callback_data=f"post_action:delete:{post_id}"
    )])
    
    buttons.append([InlineKeyboardButton(
        text="🏠 В меню",
        callback_data="main_menu"
    )])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ==================== УТИЛИТЫ ====================

def get_remove_keyboard() -> ReplyKeyboardRemove:
    """Удалить Reply клавиатуру"""
    return ReplyKeyboardRemove()


def get_back_to_menu_keyboard() -> InlineKeyboardMarkup:
    """Простая кнопка возврата в меню"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 В меню", callback_data="main_menu")]
    ])
