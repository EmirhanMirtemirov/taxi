#!/bin/bash
# Скрипт для быстрой загрузки проекта на сервер через SCP

echo "📤 Скрипт загрузки проекта на сервер"
echo ""
read -p "Введите IP адрес сервера: " SERVER_IP
read -p "Введите имя пользователя: " USERNAME
read -p "Введите путь на сервере (по умолчанию /opt): " SERVER_PATH
SERVER_PATH=${SERVER_PATH:-/opt}

echo ""
echo "Создаю архив проекта..."
cd /Users/admin/Desktop
tar -czf taxi_bot.tar.gz --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' --exclude='*.db' taxi_bot/

echo "Загружаю на сервер..."
scp taxi_bot.tar.gz ${USERNAME}@${SERVER_IP}:${SERVER_PATH}/

echo ""
echo "✅ Загрузка завершена!"
echo ""
echo "Теперь подключитесь к серверу и выполните:"
echo "  ssh ${USERNAME}@${SERVER_IP}"
echo "  cd ${SERVER_PATH}"
echo "  tar -xzf taxi_bot.tar.gz"
echo "  cd taxi_bot"
echo "  cp .env.example .env"
echo "  nano .env  # Заполните значения"
echo "  chmod +x deploy.sh"
echo "  ./deploy.sh"
