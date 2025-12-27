# states/states.py - FSM состояния бота
# Обновлённые состояния для нового флоу

from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    """Регистрация нового пользователя"""
    choosing_role = State()   # Выбор роли (водитель/пассажир)
    entering_phone = State()  # Ввод телефона
    uploading_car_photo = State()  # Загрузка фото автомобиля (только для водителей)
    entering_car_number = State()  # Ввод номера автомобиля вручную (если не распознан)


class CreatePost(StatesGroup):
    """Создание объявления"""
    entering_from = State()       # Откуда
    entering_to = State()         # Куда
    entering_time = State()       # Время выезда
    entering_seats = State()      # Кол-во мест (только для водителей)
    entering_price = State()      # Цена
    confirming = State()          # Подтверждение


class ManagePost(StatesGroup):
    """Управление объявлениями"""
    viewing = State()             # Просмотр списка
    selecting_action = State()    # Выбор действия


class Subscriptions(StatesGroup):
    """Управление подписками"""
    viewing = State()             # Просмотр списка
    adding_from = State()         # Добавление: откуда
    adding_to = State()           # Добавление: куда
    confirming_add = State()      # Подтверждение добавления
    selecting_delete = State()    # Выбор для удаления


class EditProfile(StatesGroup):
    """Редактирование профиля"""
    choosing_field = State()      # Выбор что редактировать
    editing_phone = State()       # Редактирование телефона
    changing_role = State()       # Смена роли


class Agreement(StatesGroup):
    """Согласие с правилами сервиса"""
    waiting_agreement = State()   # Ожидание согласия с правилами
