# -*- coding: utf-8 -*-
"""Nika для Android: ядро без UI.

    from nika import Engine, Store
    engine = Engine(bridge, Store("nika.json"))
    reply = engine.respond("позвони маме")
"""

__version__ = "2.5.2"

# Импорт ядра обёрнут: `python -m nika` сначала выполняет этот файл, и раньше
# любой сбой (например, файл модуля не попал в APK) убивал приложение ещё до
# того, как срабатывал обработчик ошибок в __main__.py — на телефоне это
# выглядело как «заставка на секунду и вылет». Теперь сбой запоминается, а
# понятная ошибка доходит до экрана «запуск не удался».
_FAILED_IMPORT = ""

try:
    from .engine import Engine, Reply
    from .persona import Persona
    from .store import Store
    from .weather import Weather
except Exception:  # noqa: BLE001 — показать причину, а не молча умереть
    import traceback as _traceback

    _FAILED_IMPORT = _traceback.format_exc()

    def __getattr__(name):
        if name in ("Engine", "Reply", "Persona", "Store", "Weather"):
            raise ImportError("не загрузилось ядро Nika:\n" + _FAILED_IMPORT)
        raise AttributeError(name)

__all__ = ["Engine", "Reply", "Persona", "Store", "Weather", "__version__"]
