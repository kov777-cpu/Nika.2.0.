# -*- coding: utf-8 -*-
"""Nika для Android: ядро без UI.

    from nika import Engine, Store
    engine = Engine(bridge, Store("nika.json"))
    reply = engine.respond("позвони маме")
"""

__version__ = "2.2.0"

from .engine import Engine, Reply
from .persona import Persona
from .store import Store
from .weather import Weather

__all__ = ["Engine", "Reply", "Persona", "Store", "Weather", "__version__"]

