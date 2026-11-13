# -*- coding: utf-8 -*-
"""Фразовый прогон: ни одна реплика не должна ронять обработчик.

Если внутри engine падает исключение, он печатает «[Nika/engine] ...» и
переходит к следующему обработчику. Тест ловит такие случаи и проверяет,
что на всё есть осмысленный ответ.
"""

import contextlib
import io
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from nika import Engine, Reply, Store  # noqa: E402
from nika.knowledge import Knowledge  # noqa: E402
from nika.weather import Weather  # noqa: E402
from fake_bridge import FakeBridge  # noqa: E402
from fake_knowledge import fake_knowledge_http  # noqa: E402
from tmp_utils import temp_dir  # noqa: E402


def fake_http(url):
    if "geocoding" in url:
        return json.dumps({"results": [{"name": "Москва", "latitude": 55.7, "longitude": 37.6}]})
    return json.dumps({
        "current": {"temperature_2m": 3.0, "apparent_temperature": 0.0,
                    "weather_code": 3, "wind_speed_10m": 2.0},
        "daily": {"temperature_2m_max": [5.0, 4.0], "temperature_2m_min": [0.0, -1.0],
                  "weather_code": [3, 0]},
    })


PHRASES = [
    # приветствия и болтовня
    "привет", "приветик", "доброе утро", "добрый вечер", "здравствуйте",
    "как дела", "как ты", "как жизнь", "что делаешь", "что нового",
    "поговори со мной", "расскажи о себе", "ты бот", "ты человек",
    "мне грустно", "мне плохо", "я устал", "я злюсь", "тревожно", "одиноко",
    "я заболел", "я голоден", "у меня получилось", "не получается",
    "поддержи меня", "дай совет", "посоветуй что-нибудь", "пошути", "анекдот",
    "расскажи факт", "удиви меня", "скучно", "что посмотреть", "что послушать",
    "ты красивая", "ты дура", "извини", "спасибо", "пока", "спокойной ночи",
    "люблю тебя", "давай дружить", "ау", "да", "нет", "не знаю", "нормально",
    "а ещё", "ещё", "привет, как дела?", "что ты умеешь", "помощь",
    "кто ты", "как тебя зовут", "сколько тебе лет",
    # время и напоминания
    "сколько времени", "какое сегодня число", "какой сегодня день",
    "засеки 10 минут", "таймер на полчаса", "засеки", "5 минут",
    "будильник на 7:30", "поставь будильник на 7 вечера", "будильник", "8:15",
    "напомни через 20 минут выпить воды", "напомни в 18:30 позвонить маме",
    "напомни", "через час", "мои напоминания",
    # звонки и смс
    "позвони маме", "позвони папе", "позвони в скорую", "позвони 89601234567",
    "набери 112", "позвони дяде степе", "позвони",
    "напиши смс маме я скоро буду", "отправь сообщение папе: я на работе",
    "напиши смс папе",
    # приложения и сайты
    "открой ютуб", "открой телеграм", "открой вконтакте", "открой госуслуги",
    "открой whatsapp", "открой youtube.com", "открой https://ya.ru",
    "открой настройки", "открой настройки вайфая", "открой камеру",
    "запусти калькулятор", "покажи заметки", "открой", "открой непонятночто",
    # интернет
    "найди рецепт борща", "загугли погоду", "что такое квантовая физика",
    "кто такой юрий гагарин", "поищи в интернете билеты",
    # телефон
    "заряд", "сколько процентов", "фонарик", "выключи фонарик",
    "громче", "тише", "без звука", "на полную",
    "какой пароль от вайфая", "пароль от вайфая Home_5G", "какие сети",
    "какой у меня вайфай", "выключи вайфай", "пароль от сети Office",
    "погода", "погода в москве", "погода завтра", "москва",
    # память
    "меня зовут Егор", "мне 30 лет", "я живу в Казани", "я люблю пиццу",
    "как меня зовут", "сколько мне лет", "что ты обо мне помнишь",
    "запиши купить хлеб", "мои заметки", "удали заметку 1",
    "запомни: код домофона - 1234", "какой код домофона",
    "научись: вруби ютуб = открой ютуб", "вруби ютуб",
    "что ты не знаешь", "забудь непонимание",
    # сложные и опечатки
    "аткрой ютуб", "пазвони маме", "открой ютуб и позвони папе",
    "засеки 5 минут; включи музыку", "включи музыку", "включи фильм",
    "включи песню кино", "как работает квантовая запутанность?",
    "фывапролдж", "тебя зовут Петя", "забудь обо мне",
]


class FuzzTests(unittest.TestCase):
    def setUp(self):
        folder = temp_dir("nika_fuzz_")
        self.store = Store(os.path.join(folder, "nika.json"))
        self.bridge = FakeBridge()
        self.engine = Engine(self.bridge, self.store, now=lambda: 1700000000.0,
                             weather=Weather(http_get=fake_http),
                             knowledge=Knowledge(http_get=fake_knowledge_http))

    def test_no_handler_crashes(self):
        for phrase in PHRASES:
            with self.subTest(phrase=phrase):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    reply = self.engine.respond(phrase)
                printed = out.getvalue()
                self.assertNotIn("[Nika/engine]", printed,
                                 "обработчик упал на «%s»: %s" % (phrase, printed))
                self.assertIsInstance(reply, Reply)
                self.assertTrue((reply.text or "").strip(),
                                "пустой ответ на «%s»" % phrase)
                self.assertLess(len(reply.text), 1500,
                                "слишком длинный ответ на «%s»" % phrase)

    def test_pending_chain(self):
        """Цепочка уточнений не зацикливается и не съедает команды."""
        self.engine.respond("позвони")
        self.assertIsNotNone(self.engine.pending)
        self.engine.respond("мама")
        self.assertIsNone(self.engine.pending)
        self.assertTrue(self.bridge.dialed)

    def test_commands_survive_pending(self):
        self.engine.pending = {"kind": "weather_city"}
        reply = self.engine.respond("что ты умеешь")
        self.assertIn("позвони", reply.text.lower())

    def test_repeat_phrases_do_not_crash(self):
        for _ in range(3):
            for phrase in ("привет", "пошути", "что ты умеешь", "заряд"):
                self.engine.respond(phrase)


if __name__ == "__main__":
    unittest.main(verbosity=2)
