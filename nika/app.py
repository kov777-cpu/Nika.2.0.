# -*- coding: utf-8 -*-
"""Nika для Android на BeeWare: Toga + Briefcase.

Интерфейс собран из нативных виджетов Toga: заголовок, лента сообщений,
подсказки-кнопки, строка ввода, таймер сверху. Палитра — из Windows-версии.

Вся логика (engine / persona / nlp / store) не зависит от UI и проверяется
тестами на компьютере; здесь только представление и фоновые задачи.
"""

import asyncio
import functools
import math
import os
import random
import sys
import textwrap
import threading
import time
import traceback

import toga
from toga.style import Pack

from . import Engine, Reply, Store, __version__, nlp, theme
from .bridge import get_bridge

# Полоса «волн» голосового ввода: высота и частота кадров.
WAVE_HEIGHT = 56
WAVE_FRAME_SECONDS = 0.1


def _pack(**kwargs):
    """Стиль с запасным вариантом.

    На разных версиях Toga набор свойств Pack чуть отличается. Если свойство
    не поддержано, лучше потерять оформление, чем уронить всё приложение.
    """
    try:
        return Pack(**kwargs)
    except BaseException:
        for key in ("background_color", "gap", "text_align", "font_weight",
                    "color", "font_size", "padding", "align_items",
                    "justify_content", "margin"):
            kwargs.pop(key, None)
        return Pack(**kwargs)


def wrap_phone_text(text, columns=38):
    """Переносит длинные строки, чтобы текст не уезжал за экран телефона."""
    columns = max(16, int(columns or 38))
    result = []
    for paragraph in str(text or "").split("\n"):
        if not paragraph.strip():
            result.append("")
            continue
        result.extend(textwrap.wrap(paragraph, width=columns,
                                    break_long_words=True,
                                    break_on_hyphens=True) or [""])
    return "\n".join(result)


class NikaApp(toga.App):
    # ------------------------------------------------------------------
    #  Запуск
    # ------------------------------------------------------------------
    def __init__(self):
        super().__init__("Nika", "org.nikaassistant.nika")
        self.store = None
        self.engine = None
        self.bridge = None
        self._loop = None
        self._busy = False
        self._voice = True
        self._timers = []
        self._typing = None
        self._typing_label = None
        self._timer_row = None
        self._timer_label = None
        self._timer_shown = False
        self._ticker_task = None
        self._ticker_active = False
        self._columns = 38
        self._last_activity = time.time()
        self._next_idle = time.time() + random.randint(20 * 60, 40 * 60)

        # голосовой ввод: волны, живой уровень микрофона и панель «слушаю»
        self._listening = False
        self._listen_future = None
        self._mic_cancelled = False
        self._mic_denied = False
        self._demoing = False
        self._voice_level = 0.0
        self._wave_amp = 0.0
        self._wave_run = False
        self._wave_task = None
        self._wave_bars = []
        self._wave_noise = []
        self._wave_canvas = None
        self._wave_inner = 0
        self._pixel_ratio = 1.0
        self._voice_panel = None
        self._voice_caption = None
        self._top_line = None
        self._bottom_line = None
        self._input_row = None
        self.mic_button = None

        # портрет «как ты выглядишь» — отдельный экран поверх чата
        self._look_open = False
        self._look_overlay = None
        self._look_canvas = None
        self._look_task = None
        self._look_size = (0, 0)
        self._look_progress = 1.0

        # диагностика запуска: если прошлый старт не дожил до конца — безопасный режим
        self._safe_mode = False
        self._data_dir = None
        self._boot_file = None
        self._log_file = None

    def startup(self):
        self._boot_marker()
        sys.excepthook = self._excepthook
        self._log("boot start, safe=%s" % self._safe_mode)
        try:
            self._startup_inner()
        except BaseException:
            details = traceback.format_exc()
            self._log("startup crashed:\n" + details)
            self._show_crash(details)
            return
        self._log("boot ok")
        try:
            timer = threading.Timer(8.0, self._clear_boot_marker)
            timer.daemon = True
            timer.start()
        except BaseException:
            pass

    def _stage(self, text):
        """Тост на экране: если приложение упадёт, видно, до какого шага дошло."""
        self._log("stage: " + text)
        try:
            self.bridge.toast("Nika %s: %s" % (__version__, text))
        except BaseException:
            pass

    def _startup_inner(self):
        self._prepare_data()
        self._stage("1/4 данные и голос")
        try:
            self._pixel_ratio = float(self.bridge.pixel_ratio() or 1.0)
        except BaseException:
            self._pixel_ratio = 1.0
        try:
            pitch = self.store.pref("pitch")
            rate = self.store.pref("rate")
            if pitch is not None or rate is not None:
                self.bridge.apply_voice_profile(
                    float(pitch) if pitch is not None else 1.16,
                    float(rate) if rate is not None else 0.94)
        except BaseException:
            pass
        self._stage("2/4 интерфейс")
        self.main_window = toga.MainWindow(title="Nika")
        try:
            content = self._build_ui()
        except BaseException:
            self._log("build_ui crashed:\n" + traceback.format_exc())
            self._safe_mode = True
            content = self._build_ui_safe()
        self.main_window.content = content
        self.main_window.show()
        self._stage("3/4 окно")

        # системная шапка с названием приложения не нужна — только чат
        try:
            self.bridge.hide_system_bars()
        except BaseException:
            pass
        # клавиатура должна поджимать окно, а не закрывать строку ввода
        try:
            self.bridge.prepare_window()
        except BaseException:
            pass
        try:
            self.main_window.title = ""
        except BaseException:
            pass

        except BaseException:
            pass

        self._layout_width = self._content_width()
        self._columns = max(26, min(32, int(self._layout_width / 11)))
        self._care_since = time.time()
        self._start_ticker()
        self._greet()
        self._stage("4/4 готово")

        if self._safe_mode:
            self._add_message(
                "прошлый запуск не удался, поэтому включила безопасный режим: "
                "волны и портрет будут проще. если всё в порядке — просто "
                "перезапусти приложение.", False)

        # на Android 13+ без этого разрешения не будет уведомлений от таймеров
        if getattr(self.bridge, "is_android", False):
            try:
                self.bridge.request_permissions(["POST_NOTIFICATIONS"],
                                                lambda ok: None)
            except BaseException:
                pass

    # ------------------------------------------------------------------
    #  Диагностика запуска
    # ------------------------------------------------------------------
    def _boot_marker(self):
        path = None
        try:
            data_dir = str(self.paths.data)
            os.makedirs(data_dir, exist_ok=True)
            self._data_dir = data_dir
            path = os.path.join(data_dir, "nika_boot.flag")
        except BaseException:
            pass
        if not path:
            base = os.path.join(os.path.expanduser("~"), ".nika")
            self._data_dir = base
            path = os.path.join(base, "nika_boot.flag")
        self._boot_file = path
        self._log_file = os.path.join(self._data_dir, "nika_error.log")
        try:
            if os.path.exists(path):
                self._safe_mode = True
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(str(time.time()))
        except BaseException:
            self._boot_file = None

    def _clear_boot_marker(self):
        try:
            if self._boot_file and os.path.exists(self._boot_file):
                os.remove(self._boot_file)
        except BaseException:
            pass

    def _log(self, text):
        line = "%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text)
        try:
            print("[Nika] " + text)
        except BaseException:
            pass
        try:
            if not self._log_file:
                return
            if os.path.exists(self._log_file) and \
                    os.path.getsize(self._log_file) > 64 * 1024:
                os.replace(self._log_file, self._log_file + ".old")
            with open(self._log_file, "a", encoding="utf-8") as handle:
                handle.write(line)
        except BaseException:
            pass

    def _excepthook(self, kind, value, tb):
        details = "".join(traceback.format_exception(kind, value, tb))
        self._log("unhandled:\n" + details)
        try:
            sys.__excepthook__(kind, value, tb)
        except BaseException:
            pass

    def _show_crash(self, details):
        """Вместо молчаливого падения — экран с текстом ошибки."""
        try:
            if getattr(self, "main_window", None) is None:
                self.main_window = toga.MainWindow(title="Nika")
            box = toga.Box(style=_pack(direction="column",
                                       background_color=theme.BG, padding=12))
            box.add(toga.Label(
                "запуск не удался (Nika %s)" % __version__,
                style=_pack(color=theme.ACCENT, font_size=18, font_weight="bold")))
            box.add(toga.Label(
                details[-1100:],
                style=_pack(color=theme.MUTED_LIGHT, font_size=11,
                            width=self._content_width())))
            box.add(toga.Label(
                "лог: %s" % (self._log_file or "nika_error.log"),
                style=_pack(color=theme.MUTED, font_size=10,
                            width=self._content_width())))
            self.main_window.content = box
            self.main_window.show()
        except BaseException:
            try:
                print(details)
            except BaseException:
                pass

    def _content_width(self):
        """Ширина контента в DIP. На Android screen.size бывает в пикселях."""
        width = 360.0
        candidates = []
        try:
            candidates.append(self.main_window)
        except BaseException:
            pass
        try:
            candidates.append(self.screens[0])
        except BaseException:
            pass
        for source in candidates:
            try:
                value = float(source.size[0])
                if value > 0:
                    width = value
                    break
            except BaseException:
                continue
        if width > 600:      # явно физические пиксели, а не DIP
            width = 360.0
        return max(280, min(460, width - 16))

    def _start_ticker(self):
        """Надёжно запускает секундный цикл таймеров и напоминаний."""
        try:
            loop = asyncio.get_running_loop()
            self._loop = loop
            self._ticker_task = loop.create_task(self._ticker())
            return
        except RuntimeError:
            pass
        try:
            self.add_background_task(self._ticker)
        except BaseException:
            pass
        try:
            loop = asyncio.get_event_loop_policy().get_event_loop()
            self._loop = loop
            self._ticker_task = loop.create_task(self._ticker())
        except BaseException:
            self._loop = None

    def _prepare_data(self):
        path = None
        try:
            data_dir = str(self.paths.data)
            os.makedirs(data_dir, exist_ok=True)
            self._data_dir = data_dir
            path = os.path.join(data_dir, "nika_memory.json")
        except BaseException:
            pass
        if not path:
            base = os.path.join(os.path.expanduser("~"), ".nika")
            os.makedirs(base, exist_ok=True)
            self._data_dir = base
            path = os.path.join(base, "nika_memory.json")

        self.store = Store(path)
        self._voice = bool(self.store.pref("voice", True))
        self.bridge, note = get_bridge(verbose=True)
        self.engine = Engine(self.bridge, self.store,
                             status_cb=self._status_from_thread)

    # ------------------------------------------------------------------
    #  Интерфейс
    # ------------------------------------------------------------------
    def _build_ui(self):
        width = self._content_width()
        self._layout_width = width

        # красная рамка в 1px: акцентный внешний бокс и тёмный внутренний
        self.root = toga.Box(style=_pack(direction="column",
                                         background_color=theme.ACCENT,
                                         padding=1))
        self.body = toga.Box(style=_pack(direction="column",
                                         background_color=theme.BG,
                                         padding=(0, 0, 0, 4),
                                         flex=1))
        self.root.add(self.body)

        # ---------- шапка: только имя, кнопки голоса и помощи ----------
        header = toga.Box(style=_pack(direction="row", width=width, height=64,
                                      padding=6, gap=4))
        title = toga.Label("Nika", style=_pack(
            color=theme.ACCENT, font_size=22, font_weight="bold",
            width=max(90, width - 150), height=50, padding=(6, 6, 6, 6)))
        self.voice_button = toga.Button(
            "голос" if self._voice else "тихо",
            on_press=self._on_voice,
            style=_pack(width=86, height=48, font_size=13,
                        background_color=theme.ACCENT if self._voice else theme.CHIP,
                        color=theme.ON_ACCENT if self._voice else theme.MUTED_LIGHT))
        help_button = toga.Button(
            "?", on_press=self._on_help,
            style=_pack(width=42, height=48, font_size=15,
                        background_color=theme.CHIP, color=theme.MUTED_LIGHT))
        header.add(title)
        header.add(self.voice_button)
        header.add(help_button)
        self.body.add(header)

        # тонкая линия под шапкой: самый простой виджет, без Canvas
        self._top_line = toga.Box(style=_pack(width=width, height=1,
                                              background_color=theme.LINE))
        self.body.add(self._top_line)

        # ---------- полоса таймера (появляется при необходимости) ----------
        self._timer_row = toga.Box(style=_pack(direction="row", width=width,
                                               height=46, padding=(4, 8, 4, 8),
                                               background_color=theme.BUBBLE))
        self._timer_label = toga.Label("", style=_pack(
            width=max(120, width - 86), height=38, color=theme.ACCENT,
            font_size=13, padding=(2, 4, 2, 4)))
        self._timer_stop = toga.Button(
            "стоп", on_press=self._on_stop_timer,
            style=_pack(width=66, height=38, font_size=12,
                        background_color=theme.CHIP, color=theme.MUTED_LIGHT))
        self._timer_row.add(self._timer_label)
        self._timer_row.add(self._timer_stop)

        # ---------- лента сообщений ----------
        self.chat_box = toga.Box(style=_pack(direction="column", width=width,
                                             background_color=theme.BG,
                                             padding=4))
        self.scroll = toga.ScrollContainer(horizontal=False, vertical=True,
                                           style=_pack(flex=1,
                                                       background_color=theme.BG))
        self.scroll.content = self.chat_box
        self.body.add(self.scroll)

        # подсказки убраны: на телефоне они не влезали и мешали
        self.chips_box = toga.Box(style=_pack(direction="row", width=width))
        self.chips_scroll = None

        # линия над строкой ввода
        self._bottom_line = toga.Box(style=_pack(width=width, height=1,
                                                 background_color=theme.LINE))
        self.body.add(self._bottom_line)

        # ---------- строка ввода ----------
        self._input_row = toga.Box(style=_pack(direction="row", width=width,
                                               height=66, padding=(6, 8, 6, 10),
                                               gap=4, background_color=theme.INPUT))
        self.input = toga.TextInput(
            placeholder="напиши сообщение",
            on_confirm=self._on_confirm,
            style=_pack(width=max(120, width - 126), height=46, font_size=14,
                        background_color=theme.INPUT, color=theme.ACCENT))
        self.mic_button = toga.Button(
            "мик.", on_press=self._on_mic,
            style=_pack(width=58, height=48, font_size=12,
                        background_color=theme.CHIP, color=theme.MUTED_LIGHT))
        send = toga.Button(
            "→", on_press=self._on_send,
            style=_pack(width=46, height=48, font_size=17,
                        background_color=theme.ACCENT, color=theme.ON_ACCENT))
        self._input_row.add(self.input)
        self._input_row.add(self.mic_button)
        self._input_row.add(send)
        self.body.add(self._input_row)

        # ---------- панель голосового ввода (появляется при прослушке) ------
        # собираем её лениво, при первом нажатии «мик.», чтобы при старте
        # вообще не создавать Canvas — так запуск надёжнее на Android
        self._voice_panel = None

        return self.root

    def _build_ui_safe(self):
        """Аварийный минимальный интерфейс: только то, что было в 1.9."""
        width = int(self._layout_width or self._content_width() or 340)
        self._layout_width = width
        self.root = toga.Box(style=_pack(direction="column",
                                         background_color=theme.ACCENT,
                                         padding=1))
        self.body = toga.Box(style=_pack(direction="column",
                                         background_color=theme.BG,
                                         flex=1))
        self.root.add(self.body)

        header = toga.Box(style=_pack(direction="row", width=width, height=64,
                                      padding=6, gap=4))
        header.add(toga.Label("Nika", style=_pack(
            color=theme.ACCENT, font_size=22, font_weight="bold",
            width=max(90, width - 150), height=50)))
        self.voice_button = toga.Button(
            "голос" if self._voice else "тихо", on_press=self._on_voice,
            style=_pack(width=86, height=48, font_size=13,
                        background_color=theme.ACCENT if self._voice else theme.CHIP,
                        color=theme.ON_ACCENT if self._voice else theme.MUTED_LIGHT))
        header.add(self.voice_button)
        header.add(toga.Button("?", on_press=self._on_help,
                               style=_pack(width=42, height=48, font_size=15,
                                           background_color=theme.CHIP,
                                           color=theme.MUTED_LIGHT)))
        self.body.add(header)

        self._timer_row = toga.Box(style=_pack(direction="row", width=width,
                                               height=46,
                                               background_color=theme.BUBBLE))
        self._timer_label = toga.Label("", style=_pack(
            width=max(120, width - 86), height=38, color=theme.ACCENT,
            font_size=13))
        self._timer_stop = toga.Button(
            "стоп", on_press=self._on_stop_timer,
            style=_pack(width=66, height=38, font_size=12,
                        background_color=theme.CHIP, color=theme.MUTED_LIGHT))
        self._timer_row.add(self._timer_label)
        self._timer_row.add(self._timer_stop)
        self._timer_shown = False

        self._top_line = None
        self._bottom_line = None
        self.chat_box = toga.Box(style=_pack(direction="column", width=width,
                                             padding=4))
        self.scroll = toga.ScrollContainer(horizontal=False, vertical=True,
                                           style=_pack(flex=1))
        self.scroll.content = self.chat_box
        self.body.add(self.scroll)

        self.chips_box = toga.Box(style=_pack(direction="row", width=width))
        self.chips_scroll = None

        self._input_row = toga.Box(style=_pack(direction="row", width=width,
                                               height=66, padding=(6, 8, 6, 10),
                                               gap=4, background_color=theme.INPUT))
        self.input = toga.TextInput(
            placeholder="напиши сообщение", on_confirm=self._on_confirm,
            style=_pack(width=max(120, width - 126), height=46, font_size=14,
                        background_color=theme.INPUT, color=theme.ACCENT))
        self.mic_button = toga.Button(
            "мик.", on_press=self._on_mic,
            style=_pack(width=58, height=48, font_size=12,
                        background_color=theme.CHIP, color=theme.MUTED_LIGHT))
        self._input_row.add(self.input)
        self._input_row.add(self.mic_button)
        self._input_row.add(toga.Button(
            "→", on_press=self._on_send,
            style=_pack(width=46, height=48, font_size=17,
                        background_color=theme.ACCENT, color=theme.ON_ACCENT)))
        self.body.add(self._input_row)
        self._voice_panel = None
        return self.root

    def _ensure_voice_panel(self):
        if self._voice_panel is not None:
            return self._voice_panel
        try:
            self._voice_panel = self._build_voice_panel(self._layout_width or 340)
        except BaseException:
            self._voice_panel = None
        return self._voice_panel

    # ------------------------------------------------------------------
    #  Тонкие линии и волны
    # ------------------------------------------------------------------
    def _glitch_line(self, width, colors=None, seed=None):
        """Рваная линия толщиной ровно 1 пиксель.

        Линия собирается из обрывков: длинные куски цвета LINE, короткие —
        приглушённого акцента, между ними случайные пропуски. Из-за разной
        длины и пропусков линия выглядит рваной, а не ровной линейкой.
        """
        rnd = random.Random(seed if seed is not None else random.randrange(10 ** 6))
        palette = colors or (theme.LINE, theme.LINE, theme.MUTED, theme.ACCENT)
        line = toga.Box(style=_pack(direction="row", width=int(max(1, width)),
                                    height=1, gap=1))
        remaining = int(max(1, width))
        while remaining > 0:
            segment = min(remaining, rnd.choice((3, 4, 6, 9, 13, 18)))
            line.add(toga.Box(style=_pack(width=int(segment), height=1,
                                          background_color=rnd.choice(palette))))
            remaining -= segment
            if remaining <= 0:
                break
            gap = min(remaining, rnd.choice((2, 3, 5, 8)))
            line.add(toga.Box(style=_pack(width=int(gap), height=1)))
            remaining -= gap
        return line

    def _hairline(self, width, colors=None, seed=1):
        """Рваная линия толщиной 1 DIP.

        Раньше рисовалась на Canvas ровно в 1 физический пиксель, но Canvas
        на Android оказался слишком рискованным при старте: теперь линии —
        обычные тонкие полоски, а Canvas используется только для волн и
        портрета (и создаётся лениво).
        """
        return self._glitch_line(width, colors=colors, seed=seed)

    def _build_wave(self, width):
        """Полоса «волн»: каждая палка шириной ровно 1 пиксель.

        Рисуется на Canvas — тогда 1 пиксель это правда пиксель экрана, а не
        «примерно», и перерисовка не пересчитывает раскладку всего окна.
        Если Canvas в этой версии Toga нет — остаётся запасной вариант из
        узких Box'ов по 1px.
        """
        inner = int(max(120, width - 12))
        self._wave_inner = inner
        self._wave_canvas = None
        self._wave_bars = []
        self._wave_noise = [random.uniform(0.35, 1.0) for _ in range(256)]

        canvas_class = None
        if not self._safe_mode:
            canvas_class = getattr(toga, "Canvas", None)
        if canvas_class is not None:
            try:
                canvas = canvas_class(style=_pack(width=inner,
                                                  height=WAVE_HEIGHT))
                self._wave_canvas = canvas
                return canvas
            except BaseException:
                self._wave_canvas = None

        count = max(16, min(32, int(inner / 8)))
        gap = max(2, int((inner - count) / max(1, count - 1)))
        row = toga.Box(style=_pack(direction="row", width=inner,
                                   height=WAVE_HEIGHT, gap=gap,
                                   align_items="end"))
        for index in range(count):
            bar = toga.Box(style=_pack(
                width=1, height=2,
                background_color=(theme.ACCENT if index % 4 else theme.ACCENT_PRESS)))
            self._wave_bars.append(bar)
            row.add(bar)
        return row

    def _build_voice_panel(self, width):
        inner = int(max(120, width - 12))
        panel = toga.Box(style=_pack(direction="column", width=int(width),
                                     background_color=theme.BUBBLE,
                                     padding=(4, 0, 3, 0),
                                     align_items="center"))
        panel.add(self._build_wave(width))
        panel.add(self._hairline(inner,
                                 colors=(theme.LINE, theme.LINE, theme.ACCENT)))
        self._voice_caption = toga.Label(
            "слушаю…",
            style=_pack(width=inner, height=22, font_size=11,
                        color=theme.MUTED_LIGHT, padding=(2, 6, 1, 6)))
        panel.add(self._voice_caption)
        return panel

    def _body_index(self, widget):
        try:
            return list(self.body.children).index(widget)
        except BaseException:
            return len(self.body.children)

    def _show_voice_panel(self, visible):
        if self._voice_panel is None:
            if not visible:
                return
            if self._ensure_voice_panel() is None:
                return
        try:
            attached = self._voice_panel in self.body.children
        except BaseException:
            attached = False
        if visible and not attached:
            try:
                anchor = self._bottom_line
                if anchor is None:
                    anchor = self._input_row
                self.body.insert(self._body_index(anchor), self._voice_panel)
            except BaseException:
                try:
                    self.body.add(self._voice_panel)
                except BaseException:
                    pass
        elif not visible and attached:
            try:
                self.body.remove(self._voice_panel)
            except BaseException:
                pass

    def _set_mic(self, active):
        if self.mic_button is None:
            return
        try:
            self.mic_button.text = "стоп" if active else "мик."
            self.mic_button.style.background_color = (
                theme.ACCENT if active else theme.CHIP)
            self.mic_button.style.color = (
                theme.ON_ACCENT if active else theme.MUTED_LIGHT)
        except BaseException:
            pass

    def _set_caption(self, text):
        if self._voice_caption is None:
            return
        try:
            self._voice_caption.text = str(text or "")[:52]
        except BaseException:
            pass

    def _start_waves(self):
        self._stop_waves()
        self._wave_run = True
        self._wave_amp = 0.12
        try:
            self._wave_frame()
        except BaseException:
            pass
        try:
            self._wave_task = asyncio.get_running_loop().create_task(self._wave_loop())
        except BaseException:
            self._wave_task = None

    def _stop_waves(self):
        self._wave_run = False
        task = self._wave_task
        self._wave_task = None
        if task is not None:
            try:
                task.cancel()
            except BaseException:
                pass

    async def _wave_loop(self):
        while self._wave_run:
            try:
                self._wave_frame()
            except BaseException:
                pass
            await asyncio.sleep(WAVE_FRAME_SECONDS)

    def _wave_frame(self):
        """Один кадр волн: высота каждой палки зависит от громкости голоса."""
        if self._wave_canvas is not None:
            self._draw_wave_canvas()
            return
        bars = self._wave_bars
        if not bars:
            return
        now = time.time()
        amp = self._next_amplitude(now)
        top = WAVE_HEIGHT - 8
        for index, bar in enumerate(bars):
            spike = self._wave_noise[index % len(self._wave_noise)]
            wobble = (math.sin(now * 7.0 + index * 0.9) +
                      math.sin(now * 3.1 - index * 1.7)) * 0.5
            value = amp * (0.5 + 0.55 * abs(wobble)) * (0.55 + 0.65 * spike)
            height = 2 + int(top * min(1.0, value))
            roll = random.random()
            if roll < 0.05:          # пропуск — линия «рвётся»
                height = 1
            elif roll > 0.985:       # одиночный выброс — глитч
                height = top
            try:
                bar.style.height = int(max(1, min(top, height)))
            except BaseException:
                pass

    def _next_amplitude(self, now):
        """Плавно подтягивает амплитуду к громкости микрофона."""
        target = max(0.0, min(1.0, self._voice_level))
        speed = 0.6 if target > self._wave_amp else 0.24
        self._wave_amp += (target - self._wave_amp) * speed
        self._voice_level *= 0.8
        return max(self._wave_amp, 0.08 + 0.03 * math.sin(now * 2.4))

    def _draw_wave_canvas(self):
        """Рисует палки по 1 физическому пикселю на Canvas.

        Canvas в Toga считает координаты в DIP, поэтому масштаб делим на
        плотность экрана — и получаем ровно один пиксель, без «толстых» палок.
        """
        canvas = self._wave_canvas
        ratio = min(4.0, max(0.5, float(getattr(self, "_pixel_ratio", 1.0) or 1.0)))
        width_px = int(self._wave_inner * ratio)
        height_px = int(WAVE_HEIGHT * ratio)
        step = max(2, int(round(3.0 * ratio)))
        jitter = (0, 1, 0, 2, 1, 0, 2, 0, 1, 0, 3, 0)
        now = time.time()
        amp = self._next_amplitude(now)
        top = max(4, height_px - int(4 * ratio))
        try:
            actions = canvas.root_state.drawing_actions
            actions.clear()
            canvas.scale(1.0 / ratio, 1.0 / ratio)

            # фон панели, чтобы Canvas не светился белым на телефоне
            canvas.begin_path()
            canvas.rect(0, 0, width_px, height_px)
            canvas.fill(color=theme.BUBBLE)

            canvas.begin_path()
            peaks = []
            x = 0
            index = 0
            while x < width_px:
                spike = self._wave_noise[index % len(self._wave_noise)]
                wobble = (math.sin(now * 7.0 + index * 0.7) +
                          math.sin(now * 3.1 - index * 1.3)) * 0.5
                value = amp * (0.5 + 0.55 * abs(wobble)) * (0.55 + 0.65 * spike)
                height = 1 + int(top * min(1.0, value))
                roll = random.random()
                if roll < 0.05:          # пропуск — волна «рвётся»
                    height = 1
                elif roll > 0.985:       # одиночный выброс — глитч
                    height = top
                height = max(1, min(top, height))
                y = height_px - height
                # рваный шаг: промежутки между палками тоже неровные
                if index % 6 == 0 and height > 3:
                    peaks.append((x, y, height))
                else:
                    canvas.rect(int(x), int(y), 1, int(height))
                x += step + jitter[index % len(jitter)]
                index += 1
            canvas.fill(color=theme.ACCENT)

            if peaks:
                canvas.begin_path()
                for x, y, height in peaks:
                    canvas.rect(int(x), int(y), 1, int(height))
                canvas.fill(color=theme.ACCENT_PRESS)
            canvas.redraw()
        except BaseException:
            pass

    async def _demo_waves(self):
        """Показывает волны, когда микрофона нет (например, на компьютере)."""
        if self._demoing:
            return
        self._demoing = True
        self._show_voice_panel(True)
        self._set_caption("так это выглядит, когда я слушаю")
        self._voice_level = 0.0
        self._start_waves()
        try:
            await asyncio.sleep(2.4)
        finally:
            self._stop_waves()
            self._show_voice_panel(False)
            self._demoing = False

    # ------------------------------------------------------------------
    #  Портрет «как ты выглядишь»
    # ------------------------------------------------------------------
    def _build_look_overlay(self):
        box = toga.Box(style=_pack(direction="column",
                                   background_color=theme.BG))
        canvas_class = None
        if not self._safe_mode:
            canvas_class = getattr(toga, "Canvas", None)
        self._look_canvas = None
        if canvas_class is not None:
            try:
                self._look_canvas = canvas_class(
                    style=_pack(flex=1, background_color=theme.BG),
                    on_resize=self._on_look_resize)
                box.add(self._look_canvas)
            except BaseException:
                self._look_canvas = None
        if self._look_canvas is None:
            box.add(toga.Label(
                "я собрана из тонких линий — но эта версия Toga их не рисует.",
                style=_pack(color=theme.MUTED_LIGHT, font_size=12)))
        bottom = toga.Box(style=_pack(direction="row", height=66,
                                      background_color=theme.BG,
                                      padding=(10, 12, 10, 12),
                                      align_items="center"))
        close = toga.Button(
            "закрыть", on_press=self._close_look,
            style=_pack(width=120, height=44, font_size=13,
                        background_color=theme.CHIP, color=theme.MUTED_LIGHT))
        bottom.add(close)
        box.add(bottom)
        return box

    def _on_look_resize(self, widget, width, height, **kwargs):
        try:
            self._look_size = (int(width), int(height))
        except BaseException:
            return
        self._draw_look()

    def _draw_look(self):
        canvas = self._look_canvas
        if canvas is None:
            return
        width, height = self._look_size
        if width <= 0 or height <= 0:
            width = int(self._layout_width or 340)
            height = 600
        palette = {
            "accent": theme.ACCENT,
            "bright": theme.ACCENT_PRESS,
            "muted": theme.MUTED,
            "background": theme.BG,
        }
        try:
            from . import look
            look.draw(canvas, width, height, self._pixel_ratio, palette,
                      progress=self._look_progress, now=time.time(), margin=0.04)
        except BaseException:
            pass

    def _open_look(self):
        if self._look_open:
            return
        self._look_open = True
        self._look_progress = 0.0
        try:
            self._look_overlay = self._build_look_overlay()
            self.main_window.content = self._look_overlay
        except BaseException:
            self._look_open = False
            self._look_overlay = None
            return
        try:
            self._look_task = asyncio.get_running_loop().create_task(self._look_loop())
        except BaseException:
            self._look_task = None
            self._draw_look()

    def _close_look(self, widget=None, **kwargs):
        if not self._look_open:
            return
        self._look_open = False
        task, self._look_task = self._look_task, None
        if task is not None:
            try:
                task.cancel()
            except BaseException:
                pass
        try:
            self.main_window.content = self.root
        except BaseException:
            pass
        self._look_overlay = None
        self._look_canvas = None
        self._look_size = (0, 0)
        self._scroll_end()

    async def _look_loop(self):
        start = time.time()
        try:
            while self._look_open and time.time() - start < 1.8:
                self._look_progress = min(1.0, (time.time() - start) / 1.8)
                self._draw_look()
                await asyncio.sleep(0.05)
            self._look_progress = 1.0
            # готовый портрет живёт: линии покачиваются, по фигуре идёт блик
            while self._look_open:
                self._draw_look()
                await asyncio.sleep(0.08)
        except asyncio.CancelledError:
            pass
        except BaseException:
            pass

    # ------------------------------------------------------------------
    #  Забота
    # ------------------------------------------------------------------
    def _care_tick(self):
        # не пристаём с вопросами в первые минуты после запуска
        if time.time() - getattr(self, "_care_since", 0) < 180:
            return
        try:
            reply = self.engine.care_tick()
        except BaseException:
            return
        if not reply or not reply.text:
            return
        self._add_message(reply.text, False)
        self._set_chips(reply.chips)
        if self.store.pref("notify", True):
            try:
                self.bridge.notify("Nika", reply.text)
            except BaseException:
                pass
        try:
            self.bridge.vibrate(60)
        except BaseException:
            pass

    # ------------------------------------------------------------------
    #  Сообщения
    # ------------------------------------------------------------------
    def _add_message(self, text, mine=False):
        width = self._layout_width - 8
        row = toga.Box(style=_pack(direction="row", width=width,
                                   padding=(2, 4, 2, 4)))
        label = toga.Label(
            self._phone_text(text),
            style=_pack(width=width - 8, padding=(8, 9, 8, 9), font_size=14,
                        color=theme.USER_TEXT if mine else theme.ACCENT,
                        background_color=theme.BUBBLE_MINE if mine else theme.BUBBLE,
                        text_align="right" if mine else "left"))
        row.add(label)
        self.chat_box.add(row)
        self._scroll_end()

    def _phone_text(self, text):
        return wrap_phone_text(text, self._columns)

    def _click(self):
        """Короткий звук нажатия: системный клик, без мелодий."""
        try:
            self.bridge.click()
        except BaseException:
            pass

    def _scroll_end(self):
        """Прокручивает вниз и повторяет после перерасчёта — Toga сбрасывает позицию."""
        self._scroll_now()
        try:
            loop = asyncio.get_running_loop()
            for delay in (0.05, 0.15, 0.35, 0.8, 1.5, 2.5):
                loop.call_later(delay, self._scroll_now)
        except BaseException:
            pass

    def _scroll_now(self):
        # vertical_position — позиция в пикселях; максимум = низ
        try:
            self.scroll.vertical_position = int(self.scroll.max_vertical_position)
            return
        except BaseException:
            pass
        try:
            self.scroll.vertical_position = 10 ** 6
        except BaseException:
            pass

    def _show_typing(self, text="печатает…"):
        if self._typing is None:
            row = toga.Box(style=_pack(direction="row", padding=(3, 6, 3, 6)))
            self._typing_label = toga.Label(
                self._phone_text(text),
                style=_pack(width=self._layout_width - 24,
                            padding=(6, 8, 6, 8), font_size=12,
                            color=theme.MUTED_LIGHT))
            row.add(self._typing_label)
            self._typing = row
            self.chat_box.add(row)
        else:
            self._typing_label.text = self._phone_text(text)
        self._scroll_end()

    def _hide_typing(self):
        if self._typing is not None:
            try:
                self.chat_box.remove(self._typing)
            except BaseException:
                pass
            self._typing = None
            self._typing_label = None
            self._scroll_end()

    def _set_status(self, text):
        if self._typing is not None and self._typing_label is not None:
            self._typing_label.text = self._phone_text(text)

    def _set_chips(self, items):
        for child in list(self.chips_box.children):
            try:
                self.chips_box.remove(child)
            except BaseException:
                pass
        limit = max(9, min(16, int(self._columns * 0.45)))
        for item in list(items)[:6]:
            if not item:
                continue
            item = str(item)
            display = textwrap.shorten(item, width=limit, placeholder="…")
            width = min(int(self._columns * 7.2), 22 + int(7.0 * len(display)))
            button = toga.Button(
                display,
                on_press=functools.partial(self._on_chip, item),
                style=_pack(width=width, height=34, font_size=12,
                            background_color=theme.CHIP,
                            color=theme.MUTED_LIGHT))
            try:
                self.chips_box.add(button)
            except BaseException:
                pass

    # ------------------------------------------------------------------
    #  Действия пользователя
    # ------------------------------------------------------------------
    def _spawn(self, coro):
        """Запускает корутину в цикле Toga, даже если обработчик синхронный."""
        self._ensure_ticker()
        try:
            asyncio.get_running_loop().create_task(coro)
            return
        except RuntimeError:
            pass
        loop = self._loop
        if loop is not None:
            try:
                loop.call_soon_threadsafe(lambda: asyncio.create_task(coro))
                return
            except BaseException:
                pass
        try:
            asyncio.run(coro)
        except BaseException:
            pass

    def _ensure_ticker(self):
        if self._ticker_task is not None or self._ticker_active:
            return
        try:
            self._ticker_task = asyncio.get_running_loop().create_task(self._ticker())
        except BaseException:
            pass

    def _on_confirm(self, widget, **kwargs):
        self._click()
        self._spawn(self._send(self.input.value))

    def _on_send(self, widget, **kwargs):
        self._click()
        self._spawn(self._send(self.input.value))

    def _on_chip(self, text, widget, **kwargs):
        self._click()
        self._spawn(self._send(text))

    def _on_help(self, widget, **kwargs):
        self._click()
        self._spawn(self._send("что ты умеешь"))

    def _on_voice(self, widget, **kwargs):
        self._click()
        self._voice = not self._voice
        self.store.set_pref("voice", self._voice)
        self.store.save()
        if not self._voice:
            try:
                self.bridge.stop_speak()
            except BaseException:
                pass
        try:
            self.voice_button.text = "голос" if self._voice else "тихо"
        except BaseException:
            pass
        self._add_message(
            "снова говорю вслух)" if self._voice else
            "ок, буду молчать. пиши — я отвечу текстом)", False)
        self._remember_activity()

    def _on_stop_timer(self, widget, **kwargs):
        self._click()
        self._stop_timers(announce=True)

    def _on_mic(self, widget, **kwargs):
        self._click()
        if self._listening:
            self._cancel_listen()
            return
        self._spawn(self._mic_flow())

    async def _mic_flow(self):
        """Кнопка «мик.»: включает микрофон и показывает волны."""
        if not self.bridge.can_voice:
            await self._demo_waves()
            self._add_message("голосовой ввод работает на телефоне.", False)
            return
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._listen_future = future
        self._voice_level = 0.0
        self._listening = True
        self._mic_cancelled = False
        self._mic_denied = False
        self._set_mic(True)
        self._show_voice_panel(True)
        self._set_caption("слушаю…")
        self._start_waves()

        def on_text(text):
            def put():
                if not future.done():
                    future.set_result(text)
            try:
                loop.call_soon_threadsafe(put)
            except BaseException:
                pass

        def on_level(rms):
            # rms приходит в дБ примерно от -2 до 10 — превращаем в 0..1
            try:
                value = (float(rms) + 2.0) / 12.0
            except BaseException:
                return
            self._voice_level = max(0.0, min(1.0, value))

        def on_state(state):
            if state == "speech":
                self._set_caption("слушаю…")
            elif state == "end":
                self._set_caption("распознаю…")
            elif state == "denied":
                self._mic_denied = True

        def on_partial(text):
            if text:
                self._set_caption(text)

        self._set_caption("слушаю…")
        try:
            result = self.bridge.listen(on_text, on_level, on_state, on_partial)
        except TypeError:
            try:
                result = self.bridge.listen(on_text)
            except Exception as exc:
                self._finish_listen()
                self._add_message("микрофон не отвечает: %s" % exc, False)
                return
        except Exception as exc:
            self._finish_listen()
            self._add_message("микрофон не отвечает: %s" % exc, False)
            return

        if result is not None and not result.ok:
            self._finish_listen()
            self._add_message(result.message or "не смогла включить микрофон.", False)
            return

        try:
            text = await asyncio.wait_for(future, timeout=60)
        except asyncio.TimeoutError:
            text = None
        except asyncio.CancelledError:
            text = None
        except BaseException:
            text = None
        self._finish_listen()
        if self._mic_cancelled:
            return
        if not text:
            if self._mic_denied:
                self._add_message("без доступа к микрофону я не слышу. "
                                  "разреши его в настройках приложения.", False)
                return
            self._add_message(self.engine.p.pick([
                "не расслышала. повтори, пожалуйста.",
                "тихо как-то. скажи ещё раз?",
            ]), False)
            return
        self.input.value = text
        await self._send(text)

    def _finish_listen(self):
        """Убирает волны и возвращает кнопку в обычное состояние."""
        self._listening = False
        self._listen_future = None
        self._stop_waves()
        self._set_mic(False)
        self._show_voice_panel(False)
        try:
            self.bridge.stop_listen()
        except BaseException:
            pass

    def _cancel_listen(self):
        self._mic_cancelled = True
        future = self._listen_future
        self._finish_listen()
        try:
            if future is not None and not future.done():
                future.set_result(None)
        except BaseException:
            pass

    # ------------------------------------------------------------------
    #  Обработка фразы
    # ------------------------------------------------------------------
    async def _send(self, text):
        text = (text or "").strip()
        if not text or self._busy:
            return
        self._remember_activity()
        self.input.value = ""
        self._add_message(text, mine=True)
        self._set_chips([])
        self._busy = True
        self._show_typing("думает…")
        try:
            reply = await asyncio.to_thread(self.engine.respond, text)
        except Exception as exc:
            reply = Reply("что-то сломалось: %s" % exc)
        self._busy = False
        self._hide_typing()
        self._deliver(reply)

    def _deliver(self, reply):
        if not isinstance(reply, Reply):
            return
        if reply.text:
            self._add_message(reply.text, mine=False)
        if reply.chips:
            self._set_chips(reply.chips)
        self._run_actions(reply.actions)
        if reply.speak and reply.text and self._voice:
            self._speak(reply.text)
        try:
            self.store.save()
        except BaseException:
            pass

    def _remember_activity(self):
        self._last_activity = time.time()
        self._next_idle = time.time() + random.randint(20 * 60, 40 * 60)

    # ------------------------------------------------------------------
    #  Голос
    # ------------------------------------------------------------------
    def _speak(self, text):
        if not self.bridge.can_voice:
            return
        phrase = nlp.clean_for_speech(text)
        if not phrase:
            return
        try:
            self.bridge.speak(phrase)
        except BaseException:
            pass

    def _status_from_thread(self, text):
        loop = self._loop
        if loop is None:
            return
        try:
            loop.call_soon_threadsafe(self._set_status, text)
        except BaseException:
            pass

    # ------------------------------------------------------------------
    #  Таймеры и напоминания
    # ------------------------------------------------------------------
    def _run_actions(self, actions):
        for action in actions or []:
            kind = action.get("type")
            if kind == "timer":
                self._timers.append({"label": action.get("label", "таймер"),
                                     "end": time.time() + max(1, action.get("seconds", 60))})
                self._update_timer()
            elif kind == "timer_stop":
                self._stop_timers(announce=False)
            elif kind == "reminder":
                self._check_reminders()
            elif kind == "look":
                self._open_look()
            elif kind == "look_close":
                self._close_look()

    def _stop_timers(self, announce=True):
        had = bool(self._timers)
        self._timers = []
        self._update_timer()
        try:
            self.bridge.stop_sound()
        except BaseException:
            pass
        if had and announce:
            self._add_message("остановила таймер.", False)

    def _update_timer(self):
        if not self._timers:
            self._show_timer(False)
            return
        left = int(max(0, min(item["end"] for item in self._timers) - time.time()))
        try:
            self._timer_label.text = "таймер  %02d:%02d" % (left // 60, left % 60)
        except BaseException:
            pass
        self._show_timer(True)

    def _show_timer(self, visible):
        if visible == self._timer_shown:
            return
        self._timer_shown = visible
        if visible:
            try:
                # сразу под 1px-линией шапки, над лентой сообщений
                self.body.insert(self._body_index(self._top_line) + 1,
                                 self._timer_row)
            except BaseException:
                try:
                    self.body.add(self._timer_row)
                except BaseException:
                    pass
        else:
            try:
                self.body.remove(self._timer_row)
            except BaseException:
                pass

    def _fire_timer(self, item):
        self._add_message(self.engine.p.pick([
            "время вышло)",
            "всё, таймер закончился.",
            "дзынь! время вышло.",
        ]), False)
        label = item.get("label", "таймер")
        ringing = False
        try:
            ringing = bool(self.bridge.alarm_sound().ok)
        except BaseException:
            ringing = False
        try:
            result = self.bridge.notify("Nika — таймер",
                                        label + ": время вышло")
            if not result.ok:
                self.bridge.notify_alarm("Nika — таймер",
                                         label + ": время вышло")
        except BaseException:
            pass
        try:
            self.bridge.vibrate(150)
        except BaseException:
            pass
        if not ringing:
            self._speak("Время вышло")

    def _check_reminders(self):
        try:
            due = self.store.due_reminders()
        except BaseException:
            return
        for reminder in due:
            text = reminder.get("text", "напоминание")
            self._add_message(self.engine.p.pick([
                "напоминаю: %s" % text,
                "не забыть: %s" % text,
            ]), False)
            try:
                result = self.bridge.notify_alarm("Nika напоминает", text)
                if not result.ok:
                    self.bridge.notify("Nika напоминает", text)
                self.bridge.vibrate(150)
            except BaseException:
                pass
            self._speak("Напоминаю: " + text)
            try:
                self.store.mark_reminder_done(reminder)
            except BaseException:
                pass
        if due:
            try:
                self.store.save()
            except BaseException:
                pass

    # ------------------------------------------------------------------
    #  Фоновый цикл
    # ------------------------------------------------------------------
    async def _ticker(self, *args, **kwargs):
        if self._ticker_active:
            return
        self._ticker_active = True
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        while True:
            await asyncio.sleep(1)
            try:
                self._tick()
            except BaseException:
                pass

    def _tick(self):
        now = time.time()

        if self._timers:
            alive = []
            for item in self._timers:
                if item["end"] <= now:
                    self._fire_timer(item)
                else:
                    alive.append(item)
            if len(alive) != len(self._timers):
                self._timers = alive
            self._update_timer()

        self._flush_deferred()
        self._check_reminders()
        self._care_tick()

        if now > self._next_idle:
            if now - self._last_activity > 10 * 60:
                try:
                    reply = self.engine.idle_message()
                except BaseException:
                    reply = None
                if reply:
                    self._add_message(reply.text, False)
                    self._set_chips(reply.chips)
            self._next_idle = now + random.randint(20 * 60, 40 * 60)

    def _flush_deferred(self):
        try:
            items = self.engine.take_deferred()
        except BaseException:
            return
        for item in items:
            try:
                asyncio.create_task(self._run_deferred(item))
            except BaseException:
                pass

    async def _run_deferred(self, item):
        try:
            reply = await asyncio.to_thread(item)
        except Exception as exc:
            reply = Reply("не получилось: %s" % exc)
        if isinstance(reply, Reply):
            self._deliver(reply)

    # ------------------------------------------------------------------
    #  Приветствие
    # ------------------------------------------------------------------
    def _greet(self):
        try:
            reply = self.engine.startup()
        except Exception as exc:
            self._add_message("не смогла запуститься: %s" % exc, False)
            return
        self._add_message(reply.text, False)
        self._set_chips(reply.chips)
        try:
            self.store.save()
        except BaseException:
            pass


def main():
    return NikaApp()
