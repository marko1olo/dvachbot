import asyncio
import sys

import pytest

# --- Защита от выселения нативных модулей из sys.modules -------------------
# unittest.mock.patch.dict('sys.modules', ...) при выходе делает clear() и
# заливает сохранённый снапшот обратно. Всё, что было импортировано ВНУТРИ
# такого блока, из sys.modules исчезает. Несколько тестов импортируют внутри
# patch.dict модули, которые тянут numpy; после выхода numpy выселялся, а
# seaborn/scipy позже импортировали его ВТОРОЙ раз. Два экземпляра numpy дают
# два разных numpy._globals._NoValueType, и передача сентинела одного пакета
# в C-ufunc другого падает с
#   TypeError: int() argument must be ... not '_NoValueType'
# ломая сбор тестов у всех, кто импортирует seaborn.
#
# Импортируем тяжёлый нативный стек здесь, до любого тестового модуля: тогда он
# уже присутствует в снапшоте patch.dict и переживает восстановление.
for _module_name in ("numpy", "scipy", "scipy.stats", "pandas", "matplotlib",
                     "matplotlib.pyplot", "seaborn", "PIL.Image"):
    try:
        __import__(_module_name)
    except ImportError:
        pass  # опциональная зависимость — соответствующие тесты сами разберутся
del _module_name

# Снимок настоящих модулей, пока ни один тестовый файл ещё не импортирован.
_PRISTINE_MODULES = dict(sys.modules)


@pytest.fixture(autouse=True)
def _restore_pristine_modules():
    """
    Возвращает подменённые модули на место перед каждым тестом.

    Несколько тестовых файлов (test_main, test_get_country_by_ip,
    test_select_mirror_strategically, test_main_ujson, ...) на уровне модуля
    навсегда прописывают в sys.modules заглушки вместо aiogram / aiosqlite /
    orjson / openai / pydantic и не восстанавливают их. pytest импортирует ВСЕ
    тестовые модули на этапе сбора, поэтому к моменту запуска первого теста
    заглушки уже стоят, и не связанные с ними тесты падают: изолированно они
    проходят, в общем прогоне — нет.

    Восстановление делается ПЕРЕД тестом, а не после: загрязнение происходит на
    сборе, то есть раньше любой пост-обработки. Сами тесты-загрязнители при этом
    не ломаются — свои символы они импортировали на уровне модуля и держат
    прямые ссылки, а не смотрят в sys.modules.
    """
    for _name, _real in _PRISTINE_MODULES.items():
        if sys.modules.get(_name) is not _real:
            sys.modules[_name] = _real
    yield


@pytest.fixture(scope="session", autouse=True)
def setup_event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
