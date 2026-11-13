# -*- coding: utf-8 -*-
"""Короткие ответы из Википедии: чистка темы, сеть, обрезка текста."""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from nika.knowledge import Knowledge, clean_topic, _shorten  # noqa: E402


class CleanTopicTests(unittest.TestCase):
    def test_what_is(self):
        self.assertEqual(clean_topic("что такое квантовая физика"),
                         "квантовая физика")

    def test_who_is(self):
        self.assertEqual(clean_topic("кто такой юрий гагарин"), "юрий гагарин")

    def test_tell_about(self):
        self.assertEqual(clean_topic("расскажи мне о чёрных дырах"), "чёрных дырах")

    def test_quotes_and_punctuation(self):
        self.assertEqual(clean_topic("что такое «энтропия»?"), "энтропия")

    def test_empty(self):
        self.assertEqual(clean_topic("что такое"), "")


class ShortenTests(unittest.TestCase):
    def test_keeps_sentences(self):
        text = "Первое предложение. Второе предложение. Третье предложение. " \
               "Четвёртое предложение. Пятое."
        out = _shorten(text, limit=60)
        self.assertLessEqual(len(out), 160)
        self.assertTrue(out.endswith(".") or out.endswith("…"))

    def test_empty(self):
        self.assertEqual(_shorten(""), "")


def http_ok(url):
    if "/api/rest_v1/page/summary/" in url:
        return json.dumps({
            "type": "standard",
            "title": "Квантовая физика",
            "extract": "Квантовая физика — раздел физики. Она описывает микромир.",
            "content_urls": {"desktop": {"page": "https://ru.wikipedia.org/wiki/X"}},
        })
    return ""


def http_empty(url):
    if "list=search" in url:
        return json.dumps({"query": {"search": []}})
    return json.dumps({})


def http_offline(url):
    raise OSError("нет сети")


class KnowledgeTests(unittest.TestCase):
    def test_answer(self):
        knowledge = Knowledge(http_get=http_ok)
        info = knowledge.answer("что такое квантовая физика")
        self.assertIsNotNone(info)
        self.assertEqual(info["title"], "Квантовая физика")
        self.assertIn("раздел физики", info["text"])
        self.assertEqual(info["lang"], "ru")

    def test_cache(self):
        calls = []

        def counting(url):
            calls.append(url)
            return http_ok(url)

        knowledge = Knowledge(http_get=counting)
        knowledge.answer("что такое квантовая физика")
        knowledge.answer("что такое квантовая физика")
        self.assertEqual(len(calls), 1)

    def test_empty(self):
        knowledge = Knowledge(http_get=http_empty)
        self.assertIsNone(knowledge.answer("что такое абракадабра"))
        self.assertEqual(knowledge.last_error, "empty")

    def test_offline(self):
        knowledge = Knowledge(http_get=http_offline)
        self.assertIsNone(knowledge.answer("что такое физика"))
        self.assertEqual(knowledge.last_error, "offline")

    def test_empty_question(self):
        knowledge = Knowledge(http_get=http_ok)
        self.assertIsNone(knowledge.answer("что такое"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
