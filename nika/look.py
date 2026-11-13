# -*- coding: utf-8 -*-
"""Портрет Nika: девушка в юбке, нарисованная линиями в 1 пиксель.

Геометрия задана в «дизайнерских» единицах 100×160. Рисуем на Canvas:
каждая линия — 1 физический пиксель, поэтому портрет выглядит пиксельным.
Линии «выстраиваются»: пока идёт анимация, видно только часть контура.
"""

import math

DESIGN_W = 100.0
DESIGN_H = 160.0

ACCENT = "accent"
BRIGHT = "bright"
MUTED = "muted"


def _poly(points, color, out):
    for index in range(len(points) - 1):
        x1, y1 = points[index]
        x2, y2 = points[index + 1]
        out.append((float(x1), float(y1), float(x2), float(y2), color))


def _ellipse(cx, cy, rx, ry, steps=20, color=ACCENT, out=None, start=0.0, end=2 * math.pi):
    points = []
    for step in range(steps + 1):
        angle = start + (end - start) * step / steps
        points.append((cx + rx * math.cos(angle), cy + ry * math.sin(angle)))
    _poly(points, color, out)


def design():
    """Список отрезков (x1, y1, x2, y2, цвет) в единицах 100×160."""
    out = []

    # --- голова ---
    _ellipse(50, 24, 12.0, 12.5, 18, ACCENT, out)

    # --- волосы: дуга сверху, чёлка и длинные пряди ---
    _ellipse(50, 22.5, 15.5, 16.0, 16, MUTED, out,
             start=math.pi * 1.02, end=math.pi * 2.05)
    _poly([(34.5, 24), (32.5, 38), (33.5, 52), (32.5, 62)], MUTED, out)
    _poly([(65.5, 24), (67.5, 38), (66.5, 52), (67.5, 62)], MUTED, out)
    _poly([(33.5, 52), (32.0, 66), (33.5, 78)], MUTED, out)
    _poly([(66.5, 52), (68.0, 66), (66.5, 78)], MUTED, out)
    _poly([(36, 16), (34, 30)], MUTED, out)
    _poly([(64, 16), (66, 30)], MUTED, out)
    _poly([(41, 16), (47, 15), (53, 16), (59, 16)], MUTED, out)

    # --- лицо ---
    _poly([(43.5, 24.5), (47.0, 24.5)], BRIGHT, out)
    _poly([(53.0, 24.5), (56.5, 24.5)], BRIGHT, out)
    _poly([(44.0, 20.5), (47.0, 20.5)], MUTED, out)
    _poly([(53.0, 20.5), (56.0, 20.5)], MUTED, out)
    _poly([(48.0, 31.0), (50, 32.5), (52.0, 31.0)], ACCENT, out)

    # --- шея и плечи ---
    _poly([(47.5, 36.5), (47.5, 43.0)], ACCENT, out)
    _poly([(52.5, 36.5), (52.5, 43.0)], ACCENT, out)
    _poly([(47.5, 43.0), (30.0, 50.0)], ACCENT, out)
    _poly([(52.5, 43.0), (70.0, 50.0)], ACCENT, out)

    # --- корпус и руки ---
    _poly([(30, 50), (31.5, 59), (33, 67)], ACCENT, out)
    _poly([(70, 50), (68.5, 59), (67, 67)], ACCENT, out)
    _poly([(30, 50), (23.5, 62), (24.5, 74), (27, 80.5)], ACCENT, out)
    _poly([(70, 50), (76.5, 62), (75.5, 74), (73, 80.5)], ACCENT, out)
    _poly([(27, 80.5), (30.5, 81.5)], BRIGHT, out)
    _poly([(73, 80.5), (69.5, 81.5)], BRIGHT, out)

    # --- юбка ---
    _poly([(33, 67), (67, 67)], ACCENT, out)
    _poly([(33, 67), (18, 96)], BRIGHT, out)
    _poly([(67, 67), (82, 96)], BRIGHT, out)
    _poly([(18, 96), (29, 93), (39, 96), (50, 93), (61, 96), (71, 93), (82, 96)],
          ACCENT, out)
    _poly([(40, 67), (33, 96)], MUTED, out)
    _poly([(50, 67), (50, 95)], MUTED, out)
    _poly([(60, 67), (67, 96)], MUTED, out)

    # --- ноги и обувь ---
    _poly([(43, 96), (42, 136)], ACCENT, out)
    _poly([(57, 96), (58, 136)], ACCENT, out)
    _poly([(42, 136), (36, 141)], BRIGHT, out)
    _poly([(58, 136), (64, 141)], BRIGHT, out)

    # --- «пиксельные» штрихи вокруг ---
    _poly([(12, 66), (12, 71)], MUTED, out)
    _poly([(88, 66), (88, 71)], MUTED, out)
    _poly([(8, 104), (11, 104)], MUTED, out)
    _poly([(89, 104), (92, 104)], MUTED, out)
    _poly([(79, 52), (77, 50), (75, 52), (79, 56), (83, 52), (81, 50), (79, 52)],
          BRIGHT, out)

    return out


SEGMENTS = design()


def _bounds(segments):
    xs = [x for s in segments for x in (s[0], s[2])]
    ys = [y for s in segments for y in (s[1], s[3])]
    return min(xs), min(ys), max(xs), max(ys)


def _prepare(width, height, ratio, margin=0.06):
    """Возвращает (сегменты в пикселях, скан-линия начала/конца)."""
    wpx = max(1.0, width * ratio)
    hpx = max(1.0, height * ratio)
    scale = min(wpx / DESIGN_W, hpx / DESIGN_H) * (1.0 - 2 * margin)
    offx = (wpx - DESIGN_W * scale) / 2.0
    offy = (hpx - DESIGN_H * scale) / 2.0
    out = []
    for x1, y1, x2, y2, color in SEGMENTS:
        out.append((offx + x1 * scale, offy + y1 * scale,
                    offx + x2 * scale, offy + y2 * scale, color))
    return out, offx, offy, scale


COLOR_KEYS = {
    ACCENT: "accent",
    BRIGHT: "bright",
    MUTED: "muted",
}


def draw(canvas, width, height, ratio, palette, progress=1.0, now=None,
         margin=0.06):
    """Рисует портрет. palette — dict: accent/bright/muted/background (hex)."""
    ratio = min(4.0, max(0.5, float(ratio or 1.0)))
    segments, offx, offy, scale = _prepare(width, height, ratio, margin)
    if not segments:
        return
    progress = max(0.0, min(1.0, float(progress)))
    now = 0.0 if now is None else now

    # очередь появления: сверху вниз, чтобы контур «выстраивался»
    ordered = sorted(range(len(segments)),
                     key=lambda i: (segments[i][1] + segments[i][3]) * 0.5)
    visible = set(ordered[:max(1, int(len(ordered) * progress))]) if progress < 1.0 \
        else set(range(len(segments)))

    glitch = progress >= 1.0 and math.sin(now * 1.7) > 0.6
    groups = {}
    for index, seg in enumerate(segments):
        if index not in visible:
            continue
        x1, y1, x2, y2, color_key = seg
        if glitch and index % 11 == int(now * 3) % 11:
            shift = 2.0 if (index % 2) else -2.0
            x1 += shift
            x2 += shift
        groups.setdefault(color_key, []).append((x1, y1, x2, y2))

    canvas.root_state.drawing_actions.clear()
    canvas.scale(1.0 / ratio, 1.0 / ratio)

    canvas.begin_path()
    canvas.rect(0, 0, int(width * ratio), int(height * ratio))
    canvas.fill(color=palette.get("background", "#0d0d0f"))

    for color_key, lines in groups.items():
        canvas.begin_path()
        for x1, y1, x2, y2 in lines:
            # пиксельные координаты: линии остаются ровными в 1 px
            canvas.move_to(round(x1) + 0.5, round(y1) + 0.5)
            canvas.line_to(round(x2) + 0.5, round(y2) + 0.5)
        canvas.stroke(color=palette.get(color_key, palette.get("accent", "#c81e3a")),
                      line_width=1)

    if progress < 1.0:
        # сканирующая линия, пока портрет собирается
        scan_y = offy + (DESIGN_H * scale) * progress
        canvas.begin_path()
        canvas.move_to(0, round(scan_y) + 0.5)
        canvas.line_to(int(width * ratio), round(scan_y) + 0.5)
        canvas.stroke(color=palette.get("bright", "#e83652"), line_width=1)

    canvas.redraw()
