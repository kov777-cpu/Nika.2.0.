# -*- coding: utf-8 -*-
"""Забота: «ты поел?», «как ты?» и осмысленные ответы на них."""

import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from nika import Store  # noqa: E402
from nika.care import Care  # noqa: E402
from tmp_utils import temp_dir  # noqa: E402


def at(year=2026, month=11, day=13, hour=9, minute=0):
    return time.mktime((year, month, day, hour, minute, 0, 0, 0, -1))


def make_care():
    folder = temp_dir("nika_care_")
    store = Store(os.path.join(folder, "nika.json"))
    return Care(store), store


class CareScheduleTests(unittest.TestCase):
    def test_breakfast_due(self):
        care, _store = make_care()
        note = care.due(at(hour=9), last_seen=0)
        self.assertIsNotNone(note, "утром должно захотеться спросить про завтрак")
        self.assertEqual(note["topic"], "breakfast")
        self.assertTrue(note["text"])

    def test_not_twice_per_day(self):
        care, _store = make_care()
        note = care.due(at(hour=9), last_seen=0)
        care.mark_sent(note, at(hour=9))
        self.assertIsNone(care.due(at(hour=9, minute=40), last_seen=0))

    def test_quiet_at_night(self):
        care, _store = make_care()
        self.assertIsNone(care.due(at(hour=3), last_seen=0))

    def test_sleep_at_23(self):
        care, _store = make_care()
        note = care.due(at(hour=23, minute=10), last_seen=0)
        self.assertIsNotNone(note)
        self.assertEqual(note["topic"], "sleep")

    def test_water_slot(self):
        care, _store = make_care()
        note = care.due(at(hour=11), last_seen=0)
        self.assertIsNotNone(note)
        self.assertEqual(note["topic"], "water")

    def test_mood_afternoon(self):
        care, _store = make_care()
        note = care.due(at(hour=16), last_seen=0)
        self.assertIsNotNone(note)
        self.assertEqual(note["topic"], "mood")

    def test_skip_if_user_active(self):
        care, _store = make_care()
        self.assertIsNone(care.due(at(hour=9), last_seen=at(hour=9) - 60))

    def test_disabled(self):
        care, store = make_care()
        care.set_enabled(False)
        self.assertIsNone(care.due(at(hour=9), last_seen=0))

    def test_pending_blocks_new(self):
        care, _store = make_care()
        note = care.due(at(hour=9), last_seen=0)
        care.mark_sent(note, at(hour=9))
        self.assertIsNone(care.due(at(hour=11), last_seen=0))


class CareAnswerTests(unittest.TestCase):
    def _pending_meal(self, care, hour=13):
        care.mark_sent({"topic": "lunch", "text": "обед. ты поел?",
                        "key": "2026-11-13:lunch"}, at(hour=hour))
        return care

    def test_ate_yes_asks_what(self):
        care, _store = make_care()
        self._pending_meal(care)
        data = care.answer("поел", at(hour=13, minute=5))
        self.assertIsNotNone(data)
        self.assertIn("что", data["text"].lower())
        self.assertTrue(data["chips"])

    def test_ate_no_pushes_to_eat(self):
        care, _store = make_care()
        self._pending_meal(care)
        data = care.answer("нет, забыл", at(hour=13, minute=5))
        self.assertIsNotNone(data)
        self.assertTrue(data["text"])
        self.assertTrue(any("напомни" in chip for chip in data["chips"]))

    def test_followup_about_food(self):
        care, _store = make_care()
        self._pending_meal(care)
        care.answer("поел", at(hour=13, minute=5))
        data = care.answer("суп и салат", at(hour=13, minute=7))
        self.assertIsNotNone(data)
        self.assertTrue(data["text"])

    def test_mood_bad(self):
        care, _store = make_care()
        care.mark_sent({"topic": "mood", "text": "как ты?", "key": "2026-11-13:mood"},
                       at(hour=17))
        data = care.answer("устал очень", at(hour=17, minute=5))
        self.assertIsNotNone(data)
        self.assertTrue("рядом" in data["text"].lower() or
                        "расскажи" in data["text"].lower())

    def test_water_yes(self):
        care, _store = make_care()
        care.mark_sent({"topic": "water", "text": "попей воды", "key": "w"},
                       at(hour=11))
        data = care.answer("выпил", at(hour=11, minute=5))
        self.assertIsNotNone(data)
        self.assertTrue("умница" in data["text"].lower() or
                        "хорошо" in data["text"].lower())

    def test_sleep_yes(self):
        care, _store = make_care()
        care.mark_sent({"topic": "sleep", "text": "пора спать", "key": "s"},
                       at(hour=23))
        data = care.answer("да, ложусь", at(hour=23, minute=5))
        self.assertIn("спокойной ночи", data["text"].lower())

    def test_thanks_is_not_answer(self):
        care, _store = make_care()
        self._pending_meal(care)
        self.assertIsNone(care.answer("спасибо", at(hour=13, minute=5)))

    def test_no_pending_no_answer(self):
        care, _store = make_care()
        self.assertIsNone(care.answer("да", at(hour=13, minute=5)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
