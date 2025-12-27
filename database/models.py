# database/models.py - SQLAlchemy модели
# PostgreSQL с поддержкой массивов для ключей маршрутов

from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, 
    DECIMAL, DateTime, ForeignKey, Index, 
    CheckConstraint, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class User(Base):
    """Пользователи бота"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    role = Column(String(20), nullable=False)  # 'driver' или 'passenger'
    phone = Column(String(20), nullable=False)
    rating = Column(DECIMAL(2, 1), default=Decimal("5.0"))  # Средний рейтинг
    rating_count = Column(Integer, default=0)  # Количество оценок
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Данные автомобиля (только для водителей)
    car_photo_file_id = Column(String(255), nullable=True)  # file_id фото автомобиля
    car_number = Column(String(20), nullable=True, unique=True)  # Номер автомобиля (только в БД, не публикуется, уникальный)
    
    # Связи
    posts = relationship("Post", back_populates="author", lazy="selectin")
    subscriptions = relationship("Subscription", back_populates="user", lazy="selectin")
    
    # Индексы и ограничения
    __table_args__ = (
        Index("idx_users_car_number", "car_number"),  # Индекс для быстрого поиска по номеру
    )
    
    def __repr__(self):
        return f"<User {self.telegram_id} ({self.role})>"


class Post(Base):
    """Объявления (поездки)"""
    __tablename__ = "posts"
    
    id = Column(Integer, primary_key=True)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False)  # 'driver' или 'passenger'
    
    # Маршрут (исходный текст)
    from_place = Column(String(255), nullable=False)
    to_place = Column(String(255), nullable=False)
    
    # Ключи для матчинга (массивы PostgreSQL)
    keys_from = Column(ARRAY(Text), nullable=False)
    keys_to = Column(ARRAY(Text), nullable=False)
    
    # Детали поездки
    departure_time = Column(String(100), nullable=True)  # Время выезда (текст)
    seats = Column(Integer, nullable=True)  # Только для водителей
    price = Column(Integer, nullable=False)  # Цена в сомах (макс 220)
    
    # Статус и время
    status = Column(String(20), default="active")  # active, paused, expired, deleted
    channel_message_id = Column(BigInteger, nullable=True)  # ID сообщения в канале
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)  # created_at + 60 минут
    
    # Связи
    author = relationship("User", back_populates="posts", lazy="selectin")
    
    # Индексы
    __table_args__ = (
        Index("idx_posts_status", "status"),
        Index("idx_posts_expires_at", "expires_at"),
        Index("idx_posts_keys_from", "keys_from", postgresql_using="gin"),
        Index("idx_posts_keys_to", "keys_to", postgresql_using="gin"),
    )
    
    def __repr__(self):
        return f"<Post {self.id}: {self.from_place} → {self.to_place}>"


class Subscription(Base):
    """Подписки на маршруты"""
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Ключи маршрута для матчинга
    keys_from = Column(ARRAY(Text), nullable=False)
    keys_to = Column(ARRAY(Text), nullable=False)
    
    # Оригинальный текст (для отображения)
    from_text = Column(String(255), nullable=True)
    to_text = Column(String(255), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    user = relationship("User", back_populates="subscriptions", lazy="selectin")
    
    # Индексы и ограничения
    __table_args__ = (
        Index("idx_subscriptions_user_id", "user_id"),
        Index("idx_subscriptions_keys_from", "keys_from", postgresql_using="gin"),
        Index("idx_subscriptions_keys_to", "keys_to", postgresql_using="gin"),
        UniqueConstraint("user_id", "keys_from", "keys_to", name="uq_subscription_route"),
    )
    
    def __repr__(self):
        return f"<Subscription {self.id}: {self.keys_from} → {self.keys_to}>"


class Rating(Base):
    """Оценки пользователей"""
    __tablename__ = "ratings"
    
    id = Column(Integer, primary_key=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    stars = Column(Integer, nullable=False)  # 1-5
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    from_user = relationship("User", foreign_keys=[from_user_id], lazy="selectin")
    to_user = relationship("User", foreign_keys=[to_user_id], lazy="selectin")
    post = relationship("Post", lazy="selectin")
    
    __table_args__ = (
        CheckConstraint("stars >= 1 AND stars <= 5", name="check_stars_range"),
        UniqueConstraint("from_user_id", "to_user_id", "post_id", name="uq_rating"),
    )
    
    def __repr__(self):
        return f"<Rating {self.from_user_id} → {self.to_user_id}: {self.stars}⭐>"


class NotificationLog(Base):
    """Лог отправленных уведомлений (для предотвращения дубликатов)"""
    __tablename__ = "notifications_log"
    
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    notification_message_id = Column(BigInteger, nullable=True)  # ID сообщения уведомления в Telegram
    recipient_telegram_id = Column(BigInteger, nullable=True)  # Telegram ID получателя (для быстрого доступа)
    sent_at = Column(DateTime, default=datetime.utcnow)
    
    # Связи
    post = relationship("Post", lazy="selectin")
    recipient = relationship("User", lazy="selectin")
    
    __table_args__ = (
        UniqueConstraint("post_id", "recipient_id", name="uq_notification"),
    )
    
    def __repr__(self):
        return f"<NotificationLog post={self.post_id} → user={self.recipient_id}>"


class RatingRequest(Base):
    """Запросы на оценку (для отложенной отправки)"""
    __tablename__ = "rating_requests"
    
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    scheduled_at = Column(DateTime, nullable=False)  # Когда отправить запрос
    sent = Column(Integer, default=0)  # 0 - не отправлен, 1 - отправлен
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint("post_id", "from_user_id", "to_user_id", name="uq_rating_request"),
    )

