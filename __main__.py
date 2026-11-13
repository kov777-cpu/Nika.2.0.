# -*- coding: utf-8 -*-
"""Точка входа для Briefcase: приложение запускается как `python -m nika`."""

import os
import traceback


def _early_toast(text):
    """Тост из «голого» питона, ещё до создания Toga-приложения."""
    try:
        from java import dynamic_proxy, jclass
        from org.beeware.android import MainActivity

        activity = MainActivity.singletonThis
        if activity is None:
            return
        Runnable = jclass("java.lang.Runnable")
        Toast = jclass("android.widget.Toast")

        class Show(dynamic_proxy(Runnable)):
            def __init__(self, message):
                super().__init__()
                self.message = message

            def run(self):
                try:
                    Toast.makeText(activity, self.message,
                                   Toast.LENGTH_SHORT).show()
                except Exception:
                    pass

        activity.runOnUiThread(Show(str(text)))
    except Exception:
        pass


def _write_crash(details):
    for folder in (os.path.expanduser("~"), "/data/local/tmp", os.getcwd()):
        try:
            path = os.path.join(folder, "nika_crash.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(details)
            return path
        except Exception:
            continue
    return ""


def _fallback_app(details):
    """Если даже импорт упал — показываем текст ошибки обычным окном Toga."""
    import toga
    from toga.style import Pack

    class CrashApp(toga.App):
        def startup(self):
            self.main_window = toga.MainWindow(title="Nika")
            box = toga.Box(style=Pack(direction="column", padding=12))
            box.add(toga.Label("Nika не смогла запуститься",
                               style=Pack(font_size=18)))
            box.add(toga.Label(details[-1200:], style=Pack(font_size=11)))
            self.main_window.content = box
            self.main_window.show()

    return CrashApp("Nika", "org.nikaassistant.nika")


def main():
    _early_toast("Nika: python стартовал")
    try:
        from nika.app import main as app_main
        return app_main()
    except BaseException:
        details = traceback.format_exc()
        try:
            print("[Nika] startup import failed:\n" + details)
        except Exception:
            pass
        path = _write_crash(details)
        if path:
            details += "\n\nлог: " + path
        _early_toast("Nika: ошибка старта")
        return _fallback_app(details)


if __name__ == "__main__":
    main().main_loop()
