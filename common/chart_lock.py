"""
Единая сериализация работы с matplotlib.

matplotlib.pyplot держит ГЛОБАЛЬНОЕ состояние (rcParams + реестр фигур Gcf).
В боте три независимых генератора графиков, и все они крутятся в пулах потоков:

  * main._generate_stats_charts      -> plt.rcParams.update({...})
  * main.generate_statistics_graph   -> plt.style.use('dark_background')
  * stats_generator.generate_all_charts

plt.style.use() заменяет rcParams целиком, поэтому одновременный запуск двух
генераторов давал графики с чужими цветами и шрифтами (замерено: 10 из 12
картинок отрисовывались с неверным фоном).

Замок именно threading, а не asyncio: конкурируют OS-потоки экзекьюторов,
а не корутины. Берём его ВНУТРИ функции, выполняемой в потоке, поэтому
event loop не блокируется. RLock — чтобы вложенный вызов одного генератора
из другого не устроил самодедлок.
"""

import threading
from contextlib import contextmanager

matplotlib_lock = threading.RLock()

# Генерация всех 30 графиков — минуты работы. Ждать дольше смысла нет:
# лучше отдать пользователю ошибку, чем занять поток экзекьютора навсегда.
DEFAULT_CHART_LOCK_TIMEOUT = 600.0


class ChartLockTimeout(RuntimeError):
    """Не удалось получить замок matplotlib за отведённое время."""


@contextmanager
def matplotlib_guard(timeout: float = DEFAULT_CHART_LOCK_TIMEOUT):
    """
    Контекст-менеджер для любого кода, трогающего pyplot.

    Использование (внутри функции, запускаемой через run_in_executor/to_thread):

        with matplotlib_guard():
            plt.style.use(...)
            fig, ax = plt.subplots()
            ...
    """
    acquired = matplotlib_lock.acquire(timeout=timeout)
    if not acquired:
        raise ChartLockTimeout(f"matplotlib занят дольше {timeout} с")
    try:
        yield
    finally:
        matplotlib_lock.release()
