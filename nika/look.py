# -*- coding: utf-8 -*-
"""Портрет Nika: худая девушка в юбке, нарисованная линиями в 1 пиксель.

Геометрия задана в «дизайнерских» единицах 100×160. Тонкая талия, две дуги
вместо груди (никаких кругов), длинные волосы, чокер и полоски на ногах.
Линии «выстраиваются» при открытии и потом живут: каждая чуть покачивается,
а по фигуре бегает блик.
"""

import math

DESIGN_W = 100.0
DESIGN_H = 160.0

ACCENT = "accent"
BRIGHT = "bright"
MUTED = "muted"
COLORS = (ACCENT, BRIGHT, MUTED)


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

    # --- голова: небольшая, чтобы фигура читалась стройной ---
    _ellipse(50, 20.5, 9.5, 10.0, 18, ACCENT, out)

    # --- волосы: дуга сверху, чёлка и длинные пряди по плечам ---
    _ellipse(50, 19.0, 13.0, 13.5, 16, MUTED, out,
             start=math.pi * 1.03, end=math.pi * 1.97)
    _poly([(37.0, 20.5), (35.5, 34), (36.5, 46), (35.5, 56)], MUTED, out)
    _poly([(63.0, 20.5), (64.5, 34), (63.5, 46), (64.5, 56)], MUTED, out)
    _poly([(36.5, 46), (35.0, 57), (36.5, 66)], MUTED, out)
    _poly([(63.5, 46), (65.0, 57), (63.5, 66)], MUTED, out)
    _poly([(43, 11.5), (47, 10.5), (50, 12), (53, 10.5), (57, 11.5)], MUTED, out)

    # --- лицо ---
    _poly([(44.5, 20.5), (47.0, 20.5)], BRIGHT, out)
    _poly([(53.0, 20.5), (55.5, 20.5)], BRIGHT, out)
    _poly([(44.0, 16.8), (47.0, 16.8)], MUTED, out)
    _poly([(53.0, 16.8), (56.0, 16.8)], MUTED, out)
    _poly([(47.8, 26.5), (50, 28.0), (52.2, 26.5)], ACCENT, out)

    # --- шея, чокер и плечи ---
    _poly([(48.2, 30.2), (48.2, 35.5)], ACCENT, out)
    _poly([(51.8, 30.2), (51.8, 35.5)], ACCENT, out)
    _poly([(47.6, 32.6), (52.4, 32.6)], BRIGHT, out)
    _poly([(48.2, 35.5), (37.0, 41.0)], ACCENT, out)
    _poly([(51.8, 35.5), (63.0, 41.0)], ACCENT, out)

    # --- грудь: две дуги, без кругов ---
    _poly([(38.5, 44.0), (39.5, 48.0), (43.0, 49.5), (46.5, 48.0), (48.0, 45.0)],
          ACCENT, out)
    _poly([(61.5, 44.0), (60.5, 48.0), (57.0, 49.5), (53.5, 48.0), (52.0, 45.0)],
          ACCENT, out)

    # --- корпус: от плеч к тонкой талии ---
    _poly([(37.0, 41.0), (40.0, 46.0), (43.0, 52.5), (44.8, 58.0)], ACCENT, out)
    _poly([(63.0, 41.0), (60.0, 46.0), (57.0, 52.5), (55.2, 58.0)], ACCENT, out)
    _poly([(44.8, 58.0), (55.2, 58.0)], ACCENT, out)

    # --- руки: тонкие, вдоль тела ---
    _poly([(37.0, 41.0), (31.5, 50.0), (32.5, 60.0), (34.0, 67.5)], ACCENT, out)
    _poly([(63.0, 41.0), (68.5, 50.0), (67.5, 60.0), (66.0, 67.5)], ACCENT, out)
    _poly([(34.0, 67.5), (36.5, 68.5)], BRIGHT, out)
    _poly([(66.0, 67.5), (63.5, 68.5)], BRIGHT, out)

    # --- бёдра и расклешённая юбка ---
    _poly([(44.8, 58.0), (43.0, 62.0), (29.0, 88.0)], BRIGHT, out)
    _poly([(55.2, 58.0), (57.0, 62.0), (71.0, 88.0)], BRIGHT, out)
    _poly([(29, 88), (36.5, 85), (43.5, 88), (50, 85), (56.5, 88), (63.5, 85),
           (71, 88)], ACCENT, out)
    _poly([(46.0, 62.0), (37.5, 88.0)], MUTED, out)
    _poly([(50.0, 62.0), (50.0, 87.5)], MUTED, out)
    _poly([(54.0, 62.0), (62.5, 88.0)], MUTED, out)

    # --- длинные ноги и полоски-чулки ---
    _poly([(46.0, 88.0), (45.5, 126.0)], ACCENT, out)
    _poly([(54.0, 88.0), (54.5, 126.0)], ACCENT, out)
    _poly([(45.2, 101.0), (48.0, 101.0)], BRIGHT, out)
    _poly([(45.4, 103.0), (48.2, 103.0)], BRIGHT, out)
    _poly([(52.0, 101.0), (54.8, 101.0)], BRIGHT, out)
    _poly([(51.8, 103.0), (54.6, 103.0)], BRIGHT, out)
    _poly([(45.5, 126.0), (40.0, 130.0)], BRIGHT, out)
    _poly([(54.5, 126.0), (60.0, 130.0)], BRIGHT, out)

    # --- «пиксельные» штрихи вокруг ---
    _poly([(14, 58), (14, 62)], MUTED, out)
    _poly([(86, 58), (86, 62)], MUTED, out)
    _poly([(9, 101), (12, 101)], MUTED, out)
    _poly([(88, 101), (91, 101)], MUTED, out)
    _poly([(75, 55), (73, 53), (71, 55), (75, 59), (79, 55), (77, 53), (75, 55)],
          BRIGHT, out)

    return out


SEGMENTS = design()

_BOUNDS = (
    min(min(seg[0], seg[2]) for seg in SEGMENTS),
    min(min(seg[1], seg[3]) for seg in SEGMENTS),
    max(max(seg[0], seg[2]) for seg in SEGMENTS),
    max(max(seg[1], seg[3]) for seg in SEGMENTS),
)


def _prepare(width, height, ratio, margin=0.06):
    """Сегменты в пикселях: масштаб, центрирование, начало/конец фигуры."""
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


def draw(canvas, width, height, ratio, palette, progress=1.0, now=None,
         margin=0.06):
    """Рисует портрет.

    progress < 1 — линии «выстраиваются» сверху вниз, впереди бежит скан-линия.
    На готовом портрете каждая линия чуть покачивается, а по фигуре идёт блик.
    """
    ratio = min(4.0, max(0.5, float(ratio or 1.0)))
    segments, offx, offy, scale = _prepare(width, height, ratio, margin)
    if not segments:
        return
    progress = max(0.0, min(1.0, float(progress)))
    now = 0.0 if now is None else float(now)

    ordered = sorted(range(len(segments)),
                     key=lambda i: (segments[i][1] + segments[i][3]) * 0.5)
    visible = set(ordered[:max(1, int(len(ordered) * progress))]) if progress < 1.0 \
        else set(range(len(segments)))

    figure_top = offy + _BOUNDS[1] * scale
    figure_height = max(1.0, (_BOUNDS[3] - _BOUNDS[1]) * scale)
    # блик ходит по фигуре сверху вниз и обратно
    sweep = (1.0 - math.cos(now * 1.6)) * 0.5

    groups = {MUTED: [], ACCENT: [], BRIGHT: []}
    for index, seg in enumerate(segments):
        if index not in visible:
            continue
        x1, y1, x2, y2, color = seg
        # «живые» линии: каждая покачивается по-своему
        drift_x = math.sin(now * 1.9 + index * 0.83) * 0.9
        drift_y = math.cos(now * 1.45 + index * 0.61) * 0.7
        x1 += drift_x
        x2 += drift_x
        y1 += drift_y
        y2 += drift_y
        mid = ((y1 + y2) * 0.5 - figure_top) / figure_height
        hot = abs(mid - sweep) < 0.05
        key = BRIGHT if (hot or color == BRIGHT) else color
        groups.setdefault(key, []).append((x1, y1, x2, y2))

    canvas.root_state.drawing_actions.clear()
    canvas.scale(1.0 / ratio, 1.0 / ratio)

    canvas.begin_path()
    canvas.rect(0, 0, int(width * ratio), int(height * ratio))
    canvas.fill(color=palette.get("background", "#0d0d0f"))

    for key in (MUTED, ACCENT, BRIGHT):
        lines = groups.get(key) or []
        if not lines:
            continue
        canvas.begin_path()
        for x1, y1, x2, y2 in lines:
            canvas.move_to(round(x1) + 0.5, round(y1) + 0.5)
            canvas.line_to(round(x2) + 0.5, round(y2) + 0.5)
        canvas.stroke(color=palette.get(key, palette.get("accent", "#c81e3a")),
                      line_width=1)

    if progress < 1.0:
        scan_y = offy + (DESIGN_H * scale) * progress
        canvas.begin_path()
        canvas.move_to(0, round(scan_y) + 0.5)
        canvas.line_to(int(width * ratio), round(scan_y) + 0.5)
        canvas.stroke(color=palette.get("bright", "#e83652"), line_width=1)

    canvas.redraw()
