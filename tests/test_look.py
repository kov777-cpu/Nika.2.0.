# -*- coding: utf-8 -*-
"""Портрет из линий: геометрия и отрисовка (без Toga)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from nika import look  # noqa: E402


class FakeState:
    def __init__(self):
        self.drawing_actions = []


class FakeCanvas:
    def __init__(self):
        self.root_state = FakeState()
        self.lines = []
        self.drawn = 0
        self.strokes = []
        self.pending = None

    def scale(self, sx, sy):
        pass

    def begin_path(self):
        self.path = []

    def rect(self, *args, **kwargs):
        pass

    def fill(self, *args, **kwargs):
        pass

    def move_to(self, x, y):
        self.pending = (x, y)

    def line_to(self, x, y):
        self.lines.append((self.pending, (x, y)))
        self.pending = (x, y)

    def stroke(self, color=None, line_width=1, **kwargs):
        self.strokes.append((color, line_width))
        self.drawn += len(self.lines)

    def redraw(self):
        pass


class LookGeometryTests(unittest.TestCase):
    def test_segments_exist(self):
        self.assertGreater(len(look.SEGMENTS), 40)

    def test_inside_design_box(self):
        for x1, y1, x2, y2, _color in look.SEGMENTS:
            for x in (x1, x2):
                self.assertGreaterEqual(x, -1)
                self.assertLessEqual(x, look.DESIGN_W + 1)
            for y in (y1, y2):
                self.assertGreaterEqual(y, -1)
                self.assertLessEqual(y, look.DESIGN_H + 1)

    def test_colors(self):
        for segment in look.SEGMENTS:
            self.assertIn(segment[4], (look.ACCENT, look.BRIGHT, look.MUTED))

    def test_has_skirt_and_legs(self):
        ys = [y for segment in look.SEGMENTS for y in (segment[1], segment[3])]
        xs = [x for segment in look.SEGMENTS for x in (segment[0], segment[2])]
        self.assertGreater(max(ys), 120)   # ноги
        self.assertLess(min(xs), 20)       # юбка шире плеч
        self.assertGreater(max(xs), 80)


class LookDrawTests(unittest.TestCase):
    palette = {"accent": "#c81e3a", "bright": "#e83652",
               "muted": "#7a4a52", "background": "#0d0d0f"}

    def draw(self, progress):
        canvas = FakeCanvas()
        look.draw(canvas, 360, 640, 2.0, self.palette,
                  progress=progress, now=0.0, margin=0.05)
        return canvas

    def test_full_progress_strokes(self):
        canvas = self.draw(1.0)
        self.assertTrue(canvas.strokes)
        for _color, width in canvas.strokes:
            self.assertEqual(width, 1)

    def test_partial_progress_draws_less(self):
        full = FakeCanvas()
        look.draw(full, 360, 640, 2.0, self.palette, progress=1.0, now=0.0,
                  margin=0.05)
        partial = FakeCanvas()
        look.draw(partial, 360, 640, 2.0, self.palette, progress=0.25, now=0.0,
                  margin=0.05)
        self.assertGreater(full.drawn, partial.drawn)

    def test_draw_survives_zero_size(self):
        canvas = FakeCanvas()
        look.draw(canvas, 0, 0, 1.0, self.palette, progress=1.0, now=0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
