# config.py - Конфигурация бота
# Обновлённая версия с PostgreSQL, Redis, Celery

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram Bot
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "@admin")

# PostgreSQL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://bot:password@localhost:5432/poputchik_bot"
)

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Настройки объявлений
POST_LIFETIME_MINUTES = 60  # Время жизни объявления
MAX_PRICE = 270  # Максимальная цена в сомах

# Настройки рейтинга
RATING_REQUEST_DELAY_HOURS = 2  # Через сколько часов запрашивать рейтинг

# Интервал проверки истёкших объявлений (в секундах)
EXPIRATION_CHECK_INTERVAL = 60

# Часовой пояс
TIMEZONE = "Asia/Bishkek"

# OpenAI API для проверки фото автомобилей
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
