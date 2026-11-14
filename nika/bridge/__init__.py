# -*- coding: utf-8 -*-
"""Выбор моста: Android (BeeWare/Chaquopy), если мы на телефоне, иначе — настольный."""

import os

from .base import Bridge, Contact, Res


def _android_available():
    """Android в Briefcase определяется наличием Chaquopy-моста `java`."""
    if "ANDROID_ARGUMENT" in os.environ:
        return True
    try:
        from java import jclass
        jclass("android.os.Build")
        return True
    except Exception:
        return False


def get_bridge(verbose=False):
    """Возвращает (bridge, note). note — почему не Android, если так вышло."""
    note = ""
    if _android_available():
        try:
            from .android import AndroidBridge
            bridge = AndroidBridge()
            if bridge.ready():
                return bridge, ""
            note = "android-мост не инициализировался"
        except Exception as exc:  # noqa: BLE001
            note = "android-мост недоступен: %s" % exc
            if verbose:
                print("[Nika]", note)

    from .desktop import DesktopBridge
    return DesktopBridge(), note
