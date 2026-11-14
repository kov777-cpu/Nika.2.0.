# -*- coding: utf-8 -*-
"""Точка входа для Briefcase: приложение запускается как `python -m nika`."""

import traceback


def _fallback_app(details):
    """Если импорт приложения упал — показываем текст ошибки обычным окном."""
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
    try:
        from nika.app import main as app_main
        return app_main()
    except BaseException:
        details = traceback.format_exc()
        try:
            print("[Nika] startup import failed:\n" + details)
        except BaseException:
            pass
        return _fallback_app(details)


if __name__ == "__main__":
    main().main_loop()
