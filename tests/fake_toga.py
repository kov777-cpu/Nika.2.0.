# -*- coding: utf-8 -*-
"""Минимальная заглушка Toga для тестов интерфейса без установки BeeWare.

Позволяет прогнать настоящий `nika/app.py`: проверить, что виджеты создаются,
сообщения добавляются, кнопки связаны, а стили не содержат опечаток.
"""

import os
import sys
import types
import uuid

ALLOWED_STYLE = {
    "direction", "padding", "margin", "gap", "flex", "width", "height",
    "font_size", "font_weight", "font_family", "font_style", "color",
    "background_color", "text_align", "text_direction", "alignment",
    "align_items", "justify_content",
}


class Pack:
    def __init__(self, **kwargs):
        unknown = set(kwargs) - ALLOWED_STYLE
        if unknown:
            raise TypeError("неизвестные свойства стиля: %s" % sorted(unknown))
        self.kwargs = dict(kwargs)

    def __repr__(self):
        return "Pack(%s)" % self.kwargs


class Widget:
    def __init__(self, style=None, **kwargs):
        self.style = style
        self.children = []
        self.parent = None
        self.enabled = True

    def add(self, child):
        self.children.append(child)
        child.parent = self

    def insert(self, index, child):
        self.children.insert(index, child)
        child.parent = self

    def remove(self, child):
        self.children.remove(child)
        child.parent = None


class Box(Widget):
    pass


class Label(Widget):
    def __init__(self, text="", style=None, **kwargs):
        super().__init__(style=style)
        self.text = text


class Button(Widget):
    def __init__(self, text="", on_press=None, style=None, **kwargs):
        super().__init__(style=style)
        self.text = text
        self.on_press = on_press


class TextInput(Widget):
    def __init__(self, placeholder="", on_confirm=None, style=None, **kwargs):
        super().__init__(style=style)
        self.placeholder = placeholder
        self.on_confirm = on_confirm
        self.value = ""


class ScrollContainer(Widget):
    def __init__(self, content=None, horizontal=True, vertical=True, style=None, **kwargs):
        super().__init__(style=style)
        self.content = content
        self.horizontal = horizontal
        self.vertical = vertical
        self.vertical_position = 0.0
        self.horizontal_position = 0.0


class _CanvasState:
    def __init__(self):
        self.drawing_actions = []


class Canvas(Widget):
    """Заглушка Canvas: запоминает вызовы, чтобы тесты видели отрисовку."""

    def __init__(self, style=None, on_resize=None, **kwargs):
        super().__init__(style=style)
        self.root_state = _CanvasState()
        self.on_resize = on_resize
        self.calls = []
        self.path = []
        self.pending = None

    def scale(self, sx, sy):
        self.calls.append(("scale", sx, sy))

    def begin_path(self):
        self.path = []

    def rect(self, x, y, w, h):
        self.calls.append(("rect", x, y, w, h))

    def fill(self, color=None, **kwargs):
        self.calls.append(("fill", color))

    def move_to(self, x, y):
        self.pending = (x, y)

    def line_to(self, x, y):
        self.path.append((self.pending, (x, y)))
        self.pending = (x, y)

    def stroke(self, color=None, line_width=1, **kwargs):
        self.calls.append(("stroke", color, line_width, len(self.path)))

    def redraw(self):
        self.calls.append(("redraw",))


class MainWindow:
    def __init__(self, title="", **kwargs):
        self.title = title
        self.content = None
        self.shown = False

    def show(self):
        self.shown = True


class Paths:
    def __init__(self, root):
        self.data = root
        self.cache = root
        self.config = root
        self.logs = root


class App:
    app = None

    def __init__(self, formal_name=None, app_id=None, **kwargs):
        App.app = self
        self.formal_name = formal_name or "App"
        self.app_id = app_id or "org.example"
        root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_tmp",
                            "fake_app_" + uuid.uuid4().hex[:8])
        os.makedirs(root, exist_ok=True)
        self.paths = Paths(root)
        self.main_window = None
        self.background_tasks = []

    def add_background_task(self, task):
        self.background_tasks.append(task)

    def main_loop(self):
        return 0


def install():
    """Кладёт заглушку в sys.modules вместо настоящего toga."""
    toga_mod = types.ModuleType("toga")
    style_mod = types.ModuleType("toga.style")
    pack_mod = types.ModuleType("toga.style.pack")

    style_mod.Pack = Pack
    style_mod.pack = pack_mod
    pack_mod.Pack = Pack
    pack_mod.COLUMN = "column"
    pack_mod.ROW = "row"

    for name, obj in (("App", App), ("MainWindow", MainWindow), ("Box", Box),
                      ("Label", Label), ("Button", Button), ("TextInput", TextInput),
                      ("ScrollContainer", ScrollContainer), ("Canvas", Canvas)):
        setattr(toga_mod, name, obj)
    toga_mod.style = style_mod

    sys.modules["toga"] = toga_mod
    sys.modules["toga.style"] = style_mod
    sys.modules["toga.style.pack"] = pack_mod
    return toga_mod
