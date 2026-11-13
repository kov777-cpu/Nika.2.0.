# -*- coding: utf-8 -*-
"""Проверка команд Nika на фейковом телефоне. Запуск: python tests/test_engine.py"""

import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from nika import Engine, Store  # noqa: E402
from nika.bridge.base import Contact  # noqa: E402
from nika.knowledge import Knowledge  # noqa: E402
from nika.weather import Weather  # noqa: E402
from fake_bridge import FakeBridge  # noqa: E402
from fake_knowledge import fake_knowledge_http  # noqa: E402
from tmp_utils import temp_dir  # noqa: E402

NOW = 1700000000.0


def fake_http(url):
    if "geocoding" in url:
        return json.dumps({"results": [{
            "name": "Москва", "country": "Россия",
            "latitude": 55.75, "longitude": 37.62}]})
    return json.dumps({
        "current": {"temperature_2m": 5.4, "apparent_temperature": 2.1,
                    "relative_humidity_2m": 70, "weather_code": 61,
                    "wind_speed_10m": 4.2, "is_day": 1, "precipitation": 0.2},
        "daily": {"temperature_2m_max": [7.0, 6.0],
                  "temperature_2m_min": [1.0, 0.0],
                  "weather_code": [61, 3]},
    })


def make_engine(bridge=None, now=NOW, weather=None):
    folder = temp_dir("nika_test_")
    store = Store(os.path.join(folder, "nika.json"))
    bridge = bridge or FakeBridge()
    weather = weather or Weather(http_get=fake_http)
    knowledge = Knowledge(http_get=fake_knowledge_http)
    engine = Engine(bridge, store, now=lambda: now, weather=weather,
                    knowledge=knowledge)
    return engine, bridge, store


class CommandTests(unittest.TestCase):
    """Команды телефона: звонки, приложения, сайты."""

    def setUp(self):
        self.engine, self.bridge, self.store = make_engine()

    def say(self, text, engine=None):
        return (engine or self.engine).respond(text)

    # ---------- звонки ----------
    def test_call_contact(self):
        reply = self.say("позвони маме")
        self.assertTrue(self.bridge.dialed, reply.text)
        self.assertEqual(self.bridge.dialed[0][0], "+79990001122")
        self.assertIn("+7", reply.text)

    def test_call_emergency(self):
        self.say("позвони в скорую")
        self.assertEqual(self.bridge.dialed[-1][0], "103")

    def test_call_number(self):
        self.say("позвони 89601234567")
        self.assertEqual(self.bridge.dialed[-1][0], "+79601234567")

    def test_call_unknown_contact(self):
        reply = self.say("позвони дяде степе")
        self.assertFalse(self.bridge.dialed)
        self.assertTrue(reply.chips)

    def test_call_asks_name(self):
        reply = self.say("позвони")
        self.assertEqual(self.engine.pending["kind"], "call_name")
        self.assertTrue(reply.chips)

    def test_call_pending_choice(self):
        self.say("позвони")
        self.say("Папа")
        self.assertEqual(self.bridge.dialed[-1][0], "+79990003344")

    def test_call_ambiguous(self):
        bridge = FakeBridge(contacts=[
            Contact("Мама", "+79990001122", "8 999 000-11-22"),
            Contact("Мама", "+79995556677", "8 999 555-66-77"),
        ])
        engine, _b, _s = make_engine(bridge=bridge)
        reply = engine.respond("позвони маме")
        self.assertEqual(engine.pending["kind"], "contact_choice")
        self.assertEqual(len(reply.chips), 2)
        engine.respond("2")
        self.assertEqual(bridge.dialed[-1][0], "+79995556677")

    def test_call_choice_by_name(self):
        """Два номера на одно имя: выбираем по подписи с номером."""
        bridge = FakeBridge(contacts=[
            Contact("Мама", "+79990001122", ""),
            Contact("Мама", "+79997776655", ""),
            Contact("Мама", "+79995556677", ""),
        ])
        engine, _b, _s = make_engine(bridge=bridge)
        reply = engine.respond("позвони маме")
        self.assertEqual(engine.pending["kind"], "contact_choice")
        # в подписях видны номера, иначе одинаковые имена не различить
        self.assertTrue(all("·" in chip for chip in reply.chips), reply.chips)
        engine.respond(reply.chips[2])
        self.assertEqual(bridge.dialed[-1][0], "+79995556677")

    def test_call_prefers_exact_name(self):
        """Если «Мама» явно точнее «Мама работа», переспрашивать не нужно."""
        bridge = FakeBridge(contacts=[
            Contact("Мама", "+79990001122", ""),
            Contact("Мама работа", "+79995556677", ""),
        ])
        engine, _b, _s = make_engine(bridge=bridge)
        engine.respond("позвони маме")
        self.assertIsNone(engine.pending)
        self.assertEqual(bridge.dialed[-1][0], "+79990001122")

    def test_call_permission(self):
        bridge = FakeBridge(permissions=False)
        engine, _b, _s = make_engine(bridge=bridge)
        reply = engine.respond("позвони маме")
        self.assertIn("доступ", reply.text.lower())
        deferred = engine.take_deferred()
        self.assertEqual(len(deferred), 1)
        self.assertIn("доступ", deferred[0]().text.lower())

    def test_call_immediately_mode(self):
        reply = self.say("звони сразу")
        self.assertTrue(self.store.pref("instant_call"))
        self.assertIn("сразу", reply.text.lower())
        self.say("показывай номер")
        self.assertFalse(self.store.pref("instant_call"))

    def test_sms(self):
        reply = self.say("напиши смс маме я скоро буду")
        self.assertTrue(self.bridge.sms, reply.text)
        number, text = self.bridge.sms[-1]
        self.assertEqual(number, "+79990001122")
        self.assertEqual(text, "я скоро буду")

    def test_sms_asks_text(self):
        self.say("напиши смс папе")
        self.assertEqual(self.engine.pending["kind"], "sms_text")
        self.say("я поздно")
        self.assertEqual(self.bridge.sms[-1][1], "я поздно")

    # ---------- приложения и сайты ----------
    def test_open_app_installed(self):
        reply = self.say("открой ютуб")
        self.assertIn("com.google.android.youtube", self.bridge.launched, reply.text)

    def test_open_app_site_fallback(self):
        reply = self.say("открой госуслуги")
        self.assertTrue(any("gosuslugi" in url for url in self.bridge.opened_urls),
                        reply.text)

    def test_open_app_play_store(self):
        reply = self.say("открой whatsapp")
        self.assertTrue(any(url.startswith("market://") for url in self.bridge.opened_urls),
                        reply.text)

    def test_open_url(self):
        self.say("открой youtube.com")
        self.assertIn("https://youtube.com", self.bridge.opened_urls)

    def test_open_unknown_offers_search(self):
        reply = self.say("открой непонятночто")
        self.assertTrue(any(c.startswith("поищи") for c in reply.chips), reply.chips)

    def test_open_empty(self):
        reply = self.say("открой")
        self.assertIn("что открыть", reply.text.lower())

    def test_open_settings_wifi(self):
        self.say("открой настройки вайфая")
        self.assertIn("settings:wifi", self.bridge.opened_urls)

    def test_search(self):
        self.say("найди рецепт борща")
        self.assertTrue(any("duckduckgo" in url for url in self.bridge.opened_urls))

    def test_search_internet_prefix(self):
        self.say("найди в интернете билеты")
        url = self.bridge.opened_urls[-1]
        self.assertIn("duckduckgo", url)
        self.assertIn("q=", url)
        self.assertNotIn("интернете", url)

    def test_what_is(self):
        reply = self.say("что такое квантовая физика")
        self.assertIn("квантовая физика", reply.text.lower())
        self.assertIn("Википедия", reply.text)
        self.assertFalse(any("duckduckgo" in url for url in self.bridge.opened_urls))


class TimeTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.bridge, self.store = make_engine()

    def test_timer(self):
        reply = self.engine.respond("засеки 10 минут")
        action = reply.actions[0]
        self.assertEqual(action["type"], "timer")
        self.assertEqual(action["seconds"], 600)

    def test_timer_pending(self):
        reply = self.engine.respond("засеки")
        self.assertEqual(self.engine.pending["kind"], "timer_duration")
        self.assertTrue(reply.chips)
        reply = self.engine.respond("5 минут")
        self.assertEqual(reply.actions[0]["seconds"], 300)

    def test_timer_words(self):
        reply = self.engine.respond("таймер на полчаса")
        self.assertEqual(reply.actions[0]["seconds"], 1800)

    def test_alarm(self):
        self.engine.respond("будильник на 7:30")
        self.assertEqual(self.bridge.alarms[-1][:2], (7, 30))

    def test_alarm_evening(self):
        self.engine.respond("поставь будильник на 7 вечера")
        self.assertEqual(self.bridge.alarms[-1][:2], (19, 0))

    def test_alarm_pending(self):
        self.engine.respond("будильник")
        self.assertEqual(self.engine.pending["kind"], "alarm_time")
        self.engine.respond("8:15")
        self.assertEqual(self.bridge.alarms[-1][:2], (8, 15))

    def test_reminder_duration(self):
        reply = self.engine.respond("напомни через 20 минут выпить воды")
        action = reply.actions[0]
        self.assertEqual(action["type"], "reminder")
        self.assertAlmostEqual(action["at"], NOW + 1200, delta=1)
        self.assertEqual(action["text"], "выпить воды")
        self.assertIn("выпить воды", reply.text)

    def test_reminder_clock(self):
        reply = self.engine.respond("напомни в 18:30 позвонить маме")
        action = reply.actions[0]
        self.assertEqual(action["type"], "reminder")
        self.assertIn("позвонить маме", action["text"])
        self.assertGreater(action["at"], NOW)
        self.assertTrue(self.store.get("reminders"))

    def test_reminder_pending(self):
        self.engine.respond("напомни")
        self.assertEqual(self.engine.pending["kind"], "reminder_time")
        reply = self.engine.respond("через час выпить воды")
        self.assertEqual(reply.actions[0]["type"], "reminder")
        self.assertAlmostEqual(reply.actions[0]["at"], NOW + 3600, delta=1)

    def test_time(self):
        reply = self.engine.respond("сколько времени")
        self.assertRegex(reply.text, r"\d{2}:\d{2}")

    def test_date(self):
        reply = self.engine.respond("какое сегодня число")
        self.assertIn("сегодня", reply.text.lower())


class PhoneTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.bridge, self.store = make_engine()

    def test_battery(self):
        reply = self.engine.respond("сколько заряда")
        self.assertIn("42", reply.text)

    def test_battery_low(self):
        engine, bridge, _ = make_engine(bridge=FakeBridge(battery={"percent": 9,
                                                                  "charging": False}))
        reply = engine.respond("заряд")
        self.assertIn("9", reply.text)

    def test_torch_on_off(self):
        self.engine.respond("фонарик")
        self.engine.respond("выключи фонарик")
        self.assertEqual(self.bridge.torch_states, [True, False])

    def test_volume(self):
        self.engine.respond("сделай громче")
        self.assertEqual(self.bridge.volumes[-1], "up")

    def test_volume_mute(self):
        reply = self.engine.respond("без звука")
        self.assertIn("выключен", reply.text)

    def test_wifi_password_current(self):
        reply = self.engine.respond("какой пароль от вайфая")
        self.assertIn("secret123", reply.text)

    def test_wifi_password_named(self):
        reply = self.engine.respond("пароль от вайфая Home_5G")
        self.assertIn("secret123", reply.text)

    def test_wifi_password_unknown_network_honest(self):
        reply = self.engine.respond("пароль от вайфая Office")
        self.assertIn("android", reply.text.lower())
        self.assertIn("настройки", reply.text.lower())

    def test_wifi_saved(self):
        reply = self.engine.respond("какие сети")
        self.assertIn("Home_5G", reply.text)

    def test_wifi_info(self):
        reply = self.engine.respond("какой у меня вайфай")
        self.assertIn("Home_5G", reply.text)

    def test_wifi_toggle_explains(self):
        reply = self.engine.respond("выключи вайфай")
        self.assertIn("settings:wifi", self.bridge.opened_urls)
        self.assertIn("настройки", reply.text.lower())

    def test_weather(self):
        reply = self.engine.respond("погода в москве")
        self.assertIn("Москва", reply.text)
        self.assertIn("5", reply.text)

    def test_weather_remembers_city(self):
        self.engine.respond("погода в москве")
        reply = self.engine.respond("погода")
        self.assertIn("Москва", reply.text)

    def test_weather_no_city(self):
        reply = self.engine.respond("погода")
        self.assertEqual(self.engine.pending["kind"], "weather_city")
        self.assertTrue(reply.chips)


class TalkTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.bridge, self.store = make_engine()

    def test_hello(self):
        self.assertTrue(self.engine.respond("привет").text)

    def test_how_are_you(self):
        reply = self.engine.respond("как дела")
        self.assertTrue(len(reply.text) > 5)

    def test_help_mentions_calls(self):
        reply = self.engine.respond("что ты умеешь")
        self.assertIn("позвони", reply.text.lower())

    def test_identity(self):
        self.assertIn("Nika", self.engine.respond("кто ты").text)

    def test_thanks(self):
        self.assertTrue(self.engine.respond("спасибо").text)

    def test_bye(self):
        self.assertTrue(self.engine.respond("пока").text)

    def test_joke_and_more(self):
        first = self.engine.respond("пошути").text
        self.assertTrue(first)
        second = self.engine.respond("а ещё").text
        self.assertTrue(second)
        self.assertNotEqual(first, second)

    def test_fact(self):
        self.assertTrue(self.engine.respond("расскажи факт").text)

    def test_advice(self):
        self.assertTrue(self.engine.respond("дай совет").text)

    def test_empathy(self):
        reply = self.engine.respond("мне грустно")
        self.assertTrue(len(reply.text) > 5)

    def test_topic(self):
        reply = self.engine.respond("поговори со мной")
        self.assertTrue(reply.text)

    def test_name_guard(self):
        reply = self.engine.respond("тебя зовут Петя")
        self.assertIn("Nika", reply.text)

    def test_unknown_question_offers_search(self):
        reply = self.engine.respond("как работает квантовая запутанность?")
        self.assertTrue(any(c.startswith("поищи") for c in reply.chips), reply.chips)

    def test_fallback_logs_unknown(self):
        self.engine.respond("фывапролдж")
        self.assertTrue(self.store.get("unknown"))

    def test_variety(self):
        texts = set()
        for _ in range(6):
            texts.add(self.engine.respond("как дела").text)
        self.assertGreaterEqual(len(texts), 2)

    def test_no_double_dialog(self):
        self.engine.respond("привет")
        dialog = self.store.get("dialog")
        self.assertEqual(len(dialog), 1)
        self.assertEqual(dialog[0]["u"], "привет")


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.bridge, self.store = make_engine()

    def test_learn_synonym(self):
        self.engine.respond("научись: вруби ютуб = открой ютуб")
        self.assertIn("вруби ютуб", self.store.get("learned"))
        self.engine.respond("вруби ютуб")
        self.assertIn("com.google.android.youtube", self.bridge.launched)

    def test_fact_name(self):
        reply = self.engine.respond("меня зовут Егор")
        self.assertIn("Егор", reply.text)
        self.assertIn("Егор", self.engine.respond("как меня зовут").text)

    def test_fact_city_and_likes(self):
        self.engine.respond("я живу в Казани")
        self.engine.respond("я люблю пиццу")
        summary = self.engine.respond("что ты обо мне помнишь").text
        self.assertIn("Казан", summary)
        self.assertIn("пицц", summary)

    def test_notes(self):
        self.engine.respond("запиши купить хлеб")
        reply = self.engine.respond("мои заметки")
        self.assertIn("хлеб", reply.text)
        self.engine.respond("удали заметку 1")
        self.assertNotIn("хлеб", self.engine.respond("мои заметки").text)

    def test_memory_pair(self):
        self.engine.respond("запомни: код домофона - 1234")
        reply = self.engine.respond("какой код домофона?")
        self.assertIn("1234", reply.text)

    def test_forget_me(self):
        self.engine.respond("меня зовут Егор")
        self.engine.respond("забудь обо мне")
        self.assertNotIn("Егор", self.engine.respond("как меня зовут").text)


class MultiCommandTests(unittest.TestCase):
    def test_two_commands(self):
        engine, bridge, _ = make_engine()
        reply = engine.respond("открой ютуб и позвони папе")
        self.assertIn("com.google.android.youtube", bridge.launched)
        self.assertEqual(bridge.dialed[-1][0], "+79990003344")
        self.assertTrue(reply.text)

    def test_timer_and_music(self):
        engine, bridge, _ = make_engine()
        reply = engine.respond("засеки 5 минут; включи музыку")
        self.assertTrue(reply.actions or reply.text)


class StartupTests(unittest.TestCase):
    def test_first_start(self):
        engine, _b, _s = make_engine()
        reply = engine.startup()
        self.assertIn("Nika", reply.text)

    def test_absence(self):
        engine, _b, store = make_engine()
        store.set("stats", {"last_seen": int(NOW - 5 * 3600)})
        reply = engine.startup()
        self.assertTrue(reply.text)

    def test_idle_returns_none_when_recent(self):
        engine, _b, store = make_engine()
        store.touch()
        self.assertIsNone(engine.idle_message())


class ReminderPhrasesTests(unittest.TestCase):
    """«Можешь напомнить в 7 вечера о зарядке» и родственные фразы."""

    def setUp(self):
        self.engine, self.bridge, self.store = make_engine()

    def reminder(self, text):
        reply = self.engine.respond(text)
        self.assertTrue(reply.actions, "нет действия напоминания: %s" % reply.text)
        return reply.actions[0]

    def test_polite_may(self):
        action = self.reminder("можешь напомнить в 19:30 о зарядке")
        self.assertEqual(action["type"], "reminder")
        self.assertIn("зарядк", action["text"])
        self.assertNotIn("19:30", action["text"])

    def test_polite_evening(self):
        action = self.reminder("не мог бы ты напомнить в 7 вечера про тренировку")
        self.assertIn("тренировк", action["text"])

    def test_tomorrow(self):
        action = self.reminder("напомни завтра в 9:00 позвонить маме")
        self.assertGreater(action["at"], NOW + 20 * 3600)

    def test_about_prefix(self):
        action = self.reminder("напомни мне через 15 минут о чае")
        self.assertEqual(action["text"], "чае")

    def test_pending_gets_topic(self):
        self.engine.respond("напомни")
        reply = self.engine.respond("в 18:00 о встрече")
        self.assertTrue(reply.actions)
        self.assertIn("встреч", reply.actions[0]["text"])


class LookAndVoiceTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.bridge, self.store = make_engine()

    def test_look_action(self):
        reply = self.engine.respond("как ты выглядишь")
        self.assertTrue(reply.actions, reply.text)
        self.assertEqual(reply.actions[0]["type"], "look")
        self.assertNotIn("как дела", reply.text.lower())

    def test_look_close(self):
        reply = self.engine.respond("закрыть")
        self.assertTrue(reply.actions)
        self.assertEqual(reply.actions[0]["type"], "look_close")

    def test_voice_higher(self):
        before = self.store.pref("pitch", 1.16)
        reply = self.engine.respond("сделай голос выше")
        after = self.store.pref("pitch", 1.16)
        self.assertGreater(after, before)
        self.assertTrue(reply.text)

    def test_voice_reset(self):
        self.engine.respond("голос ниже")
        self.engine.respond("верни обычный голос")
        self.assertAlmostEqual(float(self.store.pref("pitch")), 1.16, delta=0.01)


class CareEngineTests(unittest.TestCase):
    def make(self, hour=9):
        stamp = time.mktime((2026, 11, 13, hour, 0, 0, 0, 0, -1))
        engine, bridge, store = make_engine(now=stamp)
        return engine, bridge, store

    def test_care_tick_returns_reply_once(self):
        engine, _bridge, _store = self.make(hour=9)
        reply = engine.care_tick()
        self.assertIsNotNone(reply)
        self.assertEqual(reply.intent, "care")
        self.assertTrue(reply.text)
        self.assertIsNone(engine.care_tick())

    def test_care_answer_is_contextual(self):
        engine, _bridge, _store = self.make(hour=9)
        engine.care_tick()
        reply = engine.respond("поел")
        self.assertTrue(reply.text)
        self.assertIn("что", reply.text.lower())

    def test_care_off(self):
        engine, _bridge, store = self.make(hour=9)
        reply = engine.respond("отключи заботу")
        self.assertTrue(reply.text)
        self.assertIsNone(engine.care_tick())
        self.assertFalse(store.pref("care"))

    def test_care_on_again(self):
        engine, _bridge, store = self.make(hour=9)
        engine.respond("отключи заботу")
        engine.respond("включи заботу")
        self.assertTrue(store.pref("care"))


class KnowledgeEngineTests(unittest.TestCase):
    def test_what_is_answered_in_chat(self):
        engine, bridge, _store = make_engine()
        reply = engine.respond("что такое квантовая физика")
        self.assertIn("квантовая физика", reply.text.lower())
        self.assertIn("Википедия", reply.text)
        self.assertFalse(bridge.opened_urls)

    def test_about_me_not_wiki(self):
        engine, _bridge, _store = make_engine()
        reply = engine.respond("расскажи о себе")
        self.assertNotIn("Википедия", reply.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
