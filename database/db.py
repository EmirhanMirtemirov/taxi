# database/db.py - Подключение к PostgreSQL
# Асинхронное подключение через SQLAlchemy + asyncpg

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from contextlib import asynccontextmanager
import logging

from config import DATABASE_URL

logger = logging.getLogger(__name__)

# Создаём асинхронный движок с оптимизированными настройками
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # True для отладки SQL запросов
    pool_size=15,  # Увеличиваем размер пула
    max_overflow=30,  # Увеличиваем максимальное количество соединений
    pool_pre_ping=True,  # Проверка соединений перед использованием
    pool_recycle=3600,  # Пересоздание соединений каждый час
    connect_args={
        "command_timeout": 30,  # Таймаут выполнения команд
        "server_settings": {
            "application_name": "poputchik_bot"
        }
    }
)

# Фабрика сессий
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Базовый класс для моделей
Base = declarative_base()


@asynccontextmanager
async def get_session():
    """Контекстный менеджер для работы с сессией БД с улучшенной обработкой ошибок"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка БД: {e}")
            # Добавляем детальную информацию об ошибке для отладки
            if "timeout" in str(e).lower():
                logger.warning("⚠️ Таймаут при выполнении запроса к БД - возможно, нужно оптимизировать запрос")
            elif "connection" in str(e).lower():
                logger.warning("⚠️ Проблемы с подключением к БД - проверьте доступность сервера")
            raise


async def init_db():
    """Инициализация базы данных - создание всех таблиц"""
    from database.models import Base
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("База данных инициализирована")


async def close_db():
    """Закрытие соединения с БД"""
    await engine.dispose()
    logger.info("Соединение с БД закрыто")

