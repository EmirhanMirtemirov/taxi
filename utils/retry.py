# utils/retry.py - Утилиты для повторных попыток выполнения запросов
# Помогает справиться с временными сетевыми проблемами

import asyncio
import functools
import logging
from typing import Callable, TypeVar, Any, Union

logger = logging.getLogger(__name__)

T = TypeVar('T')

async def async_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    Декоратор для повторных попыток выполнения асинхронной функции
    
    Args:
        max_attempts: Максимальное количество попыток
        delay: Начальная задержка между попытками
        backoff: Множитель для увеличения задержки
        exceptions: Кортеж исключений для обработки
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Попытка {attempt + 1}/{max_attempts} не удалась: {e}. "
                            f"Повторная попытка через {current_delay:.1f} сек..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"Все {max_attempts} попыток выполнения {func.__name__} не удались. "
                            f"Последняя ошибка: {e}"
                        )
            
            raise last_exception
        
        return wrapper
    return decorator


def sync_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    Декоратор для повторных попыток выполнения синхронной функции
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            import time
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"Попытка {attempt + 1}/{max_attempts} не удалась: {e}. "
                            f"Повторная попытка через {current_delay:.1f} сек..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"Все {max_attempts} попыток выполнения {func.__name__} не удались. "
                            f"Последняя ошибка: {e}"
                        )
            
            raise last_exception
        
        return wrapper
    return decorator


async def safe_execute_with_timeout(
    coro,
    timeout: float = 30.0,
    default_return: Any = None
) -> Any:
    """
    Безопасное выполнение корутины с таймаутом
    
    Args:
        coro: Корутина для выполнения
        timeout: Таймаут в секундах
        default_return: Значение по умолчанию при таймауте
    
    Returns:
        Результат выполнения или default_return при таймауте
    """
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"Таймаут выполнения операции через {timeout} сек")
        return default_return
    except Exception as e:
        logger.error(f"Ошибка выполнения операции: {e}")
        return default_return
