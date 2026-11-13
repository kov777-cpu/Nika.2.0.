# -*- coding: utf-8 -*-
"""Забота: «ты поел?», «попей воды», «как ты?», «пора спать».

Nika сама пишет в чат и присылает уведомление в подходящее время. Когда
человек отвечает, ответ разбирается по теме: «поел» и «не поел» получают
разные, осмысленные реплики, а не «ок» и «понятно».
"""

import random
import re
import time

QUIET_FROM = 23      # после 23:00 не лезем с вопросами (кроме «пора спать»)
QUIET_TO = 8
PENDING_HOURS = 3    # ждём ответ на заботу не дольше трёх часов
MIN_GAP_MINUTES = 35  # между заботливыми сообщениями
ACTIVE_MINUTES = 10   # человек только что писал — не отвлекаем

MEALS = (
    {
        "topic": "breakfast", "start": 8, "end": 11, "title": "завтрак",
        "texts": [
            "ты поел? не пропускай завтрак, это правда важно.",
            "доброе утро. ты уже позавтракал?",
            "завтрак был? а то кофе — не еда)",
        ],
    },
    {
        "topic": "lunch", "start": 12, "end": 15, "title": "обед",
        "texts": [
            "обед. ты поел?",
            "середина дня — самое время поесть. ты как, пообедал?",
            "напоминаю про обед) не работай до головокружения.",
        ],
    },
    {
        "topic": "dinner", "start": 18, "end": 21, "title": "ужин",
        "texts": [
            "ты поужинал? вечером особенно легко забыть про еду.",
            "ужин был? не оставляй его на «потом».",
            "пора ужинать. ты поел?",
        ],
    },
)

WATER_SLOTS = (11, 15, 17)
WATER_TEXTS = [
    "попей воды, пожалуйста. ты сегодня мало пил(а).",
    "стакан воды — и станет легче. ты пил(а)?",
    "водичка. просто напоминаю)",
]

MOOD_TEXTS = [
    "как ты? что нового?",
    "ты как вообще? я давно не спрашивала.",
    "как настроение? если тяжело — говори, я рядом.",
]

SLEEP_TEXTS = [
    "пора спать. телефон подождёт до утра.",
    "уже поздно. ты ложишься?",
    "закругляйся. завтра начнём заново.",
]

STRETCH_TEXTS = [
    "встань и разомнись на минуту, а то спина скажет спасибо.",
    "ты долго сидишь. потянись, я подожду.",
]

YES_RE = re.compile(
    r"\b(?:да|ага|угу|конечно|да\s+да|поел|поела|покушал|покушала|позавтракал|"
    r"позавтракала|пообедал|пообедала|поужинал|поужинала|выпил|выпила|сделал|"
    r"сделала|готово|уже|норм|нормально|хорошо|отлично|супер|класс|да\s+поел|"
    r"да\s+выпил)\b"
)
NO_RE = re.compile(
    r"\b(?:нет|неа|еще\s+нет|ещё\s+нет|не\s+успел|не\s+успела|забыл|забыла|"
    r"не\s+хочу|не\s+буду|позже|потом|не\s+поел|не\s+поела|не\s+пил|не\s+пила|"
    r"не\s+ел|не\s+ела|никак)\b"
)
BAD_RE = re.compile(
    r"\b(?:плохо|устал|устала|тяжело|грустно|болит|бесит|тревожно|одиноко|"
    r"не\s+выспался|не\s+выспалась|вымотался|вымоталась|депрессия|тоска)\b"
)
GOOD_RE = re.compile(r"\b(?:хорошо|отлично|супер|класс|норм|нормально|радостно|"
                     r"весело)\b")
FOOD_RE = re.compile(
    r"\b(?:суп|борщ|каша|бутерброд\w*|салат\w*|яйц\w*|омлет\w*|макарон\w*|рис|"
    r"мясо|куриц\w*|рыб\w*|пицц\w*|шаурм\w*|блин\w*|творог\w*|йогурт\w*|"
    r"кофе|чай|сосиск\w*|пельмен\w*|картошк\w*|овощ\w*|фрукт\w*|сэндвич\w*)\b"
)
ACK_RE = re.compile(r"^(?:спасибо|благодарю|ок|окей|понял|поняла|ладно|ясно|"
                    r"принято|хорошо,? спасибо)[\s.!]*$")


def _has(pattern, text):
    return bool(pattern.search(text or ""))


class Care:
    """Заботливые сообщения и ответы на них."""

    def __init__(self, store, rnd=None):
        self.store = store
        self.rnd = rnd or random.Random()

    # ------------------------------------------------------------------
    #  Состояние
    # ------------------------------------------------------------------
    def _state(self):
        state = self.store.get("care")
        if not isinstance(state, dict):
            state = {}
            self.store.set("care", state)
        state.setdefault("sent", {})
        return state

    def enabled(self):
        return bool(self.store.pref("care", True))

    def set_enabled(self, value):
        self.store.set_pref("care", bool(value))

    def pending(self, now=None):
        """Тема, на которую человек ещё не ответил."""
        now = time.time() if now is None else now
        pending = self._state().get("pending") or {}
        topic = pending.get("topic")
        at = float(pending.get("at", 0) or 0)
        if not topic or not at:
            return None
        if now - at > PENDING_HOURS * 3600:
            return None
        return pending

    def _sent(self, key):
        return float(self._state().get("sent", {}).get(key, 0) or 0)

    def _mark(self, key, now):
        state = self._state()
        state.setdefault("sent", {})[key] = now
        # не копим историю бесконечно
        sent = state["sent"]
        if len(sent) > 80:
            state["sent"] = dict(sorted(sent.items(), key=lambda kv: kv[1])[-60:])

    # ------------------------------------------------------------------
    #  Что пора сказать
    # ------------------------------------------------------------------
    def due(self, now=None, last_seen=0):
        """Возвращает {"topic", "text"} или None."""
        if not self.enabled():
            return None
        now = time.time() if now is None else now
        stamp = time.localtime(now)
        hour = stamp.tm_hour
        day = time.strftime("%Y-%m-%d", stamp)
        state = self._state()

        if hour >= QUIET_FROM or hour < QUIET_TO:
            # ночью только «пора спать»
            if not (hour == 23 and not self._sent(day + ":sleep")):
                return None

        if state.get("last") and now - float(state["last"]) < MIN_GAP_MINUTES * 60:
            return None
        if self.pending(now):
            return None
        if last_seen and now - last_seen < ACTIVE_MINUTES * 60:
            return None

        for meal in MEALS:
            if not (meal["start"] <= hour < meal["end"]):
                continue
            key = day + ":" + meal["topic"]
            if self._sent(key):
                continue
            return {"topic": meal["topic"], "text": self.rnd.choice(meal["texts"]),
                    "title": meal["title"], "key": key}

        if not self._sent(day + ":sleep") and (hour == 23 or (hour == 22 and
                                                              stamp.tm_min >= 45)):
            return {"topic": "sleep", "text": self.rnd.choice(SLEEP_TEXTS),
                    "title": "сон", "key": day + ":sleep"}

        for slot in WATER_SLOTS:
            if hour != slot:
                continue
            key = "%s:water-%d" % (day, slot)
            if self._sent(key):
                continue
            return {"topic": "water", "text": self.rnd.choice(WATER_TEXTS),
                    "title": "вода", "key": key}

        if 16 <= hour < 19 and not self._sent(day + ":mood"):
            return {"topic": "mood", "text": self.rnd.choice(MOOD_TEXTS),
                    "title": "настроение", "key": day + ":mood"}

        if 14 <= hour < 16 and not self._sent(day + ":stretch"):
            return {"topic": "stretch", "text": self.rnd.choice(STRETCH_TEXTS),
                    "title": "разминка", "key": day + ":stretch"}

        return None

    def mark_sent(self, note, now=None):
        now = time.time() if now is None else now
        state = self._state()
        state["last"] = now
        state["pending"] = {"topic": note.get("topic", ""), "at": now,
                            "text": note.get("text", "")}
        if note.get("key"):
            self._mark(note["key"], now)
        self.store.save()

    # ------------------------------------------------------------------
    #  Ответ человека
    # ------------------------------------------------------------------
    def _finish(self, text, chips=None, followup=None, now=None):
        state = self._state()
        pending = state.get("pending") or {}
        state["answered"] = {"topic": pending.get("topic", ""),
                             "at": now or time.time()}
        state["pending"] = {}
        state["followup"] = followup or {}
        self.store.save()
        return {"text": text, "chips": chips or [], "topic": pending.get("topic", "")}

    def answer(self, text, now=None):
        """Осмысленный ответ на «поел?»/«как ты?». None — если это не ответ."""
        now = time.time() if now is None else now
        clean = (text or "").strip()
        if not clean or len(clean.split()) > 12:
            return None
        if ACK_RE.match(clean.lower()):
            return None

        pending = self.pending(now)
        if pending:
            topic = pending.get("topic", "")
            if topic in ("breakfast", "lunch", "dinner"):
                return self._meal_reply(topic, clean, now)
            if topic == "water":
                return self._water_reply(clean, now)
            if topic == "mood":
                return self._mood_reply(clean, now)
            if topic == "sleep":
                return self._sleep_reply(clean, now)
            if topic == "stretch":
                return self._stretch_reply(clean, now)

        followup = self._state().get("followup") or {}
        if followup and now - float(followup.get("at", 0) or 0) < 30 * 60:
            return self._followup_reply(followup, clean, now)
        return None

    # ---------- темы ----------
    def _meal_reply(self, topic, text, now):
        meal = next((m["title"] for m in MEALS if m["topic"] == topic), "еда")
        if _has(BAD_RE, text):
            return self._finish(
                "поняла. тогда просто поешь чего-нибудь тёплого, без подвига. "
                "и скажи мне потом, что съел.", ["сейчас поем", "не хочу"], now=now)
        if _has(NO_RE, text) and not _has(YES_RE, text):
            return self._finish(
                self.rnd.choice([
                    "так, иди поешь. я подожду, честно.",
                    "не пропускай %s. даже пять минут и бутерброд — уже лучше." % meal,
                    "поешь, пожалуйста. потом вернёшься — я никуда не денусь.",
                ]),
                ["напомни через 30 минут поесть", "сейчас поем"],
                followup={"topic": "meal_wait", "at": now}, now=now)
        if _has(YES_RE, text) or _has(FOOD_RE, text):
            return self._finish(
                self.rnd.choice([
                    "молодец. а что было на %s?" % meal,
                    "вот и славно. что ел?",
                    "хорошо. тогда я спокойна) а что было?",
                ]),
                ["суп", "бутерброд", "салат", "не помню"],
                followup={"topic": "meal_food", "at": now}, now=now)
        return self._finish(
            "поняла. главное — не на бегу. я рядом, если что.",
            ["спасибо", "напомни через час поесть"], now=now)

    def _water_reply(self, text, now):
        if _has(NO_RE, text) and not _has(YES_RE, text):
            return self._finish(
                self.rnd.choice([
                    "сделай глоток прямо сейчас, я подожду. правда помогает.",
                    "ну хоть полстакана. потом скажешь, что выпил)",
                ]),
                ["выпил", "напомни через час"], now=now)
        return self._finish(
            self.rnd.choice([
                "вот и умница. ещё стакан вечером — и совсем хорошо.",
                "хорошо. тогда я спокойна за твои почки)",
            ]),
            ["спасибо"], now=now)

    def _mood_reply(self, text, now):
        if _has(BAD_RE, text):
            return self._finish(
                self.rnd.choice([
                    "я рядом. расскажи, что случилось?",
                    "поняла. расскажи, что случилось — я не убегу.",
                ]),
                ["устал", "поругался", "просто так"], now=now)
        if _has(GOOD_RE, text):
            return self._finish(
                self.rnd.choice([
                    "рада) а что хорошего случилось?",
                    "приятно слышать. чем занимался?",
                ]),
                ["ничего особенного", "работа", "гулял"], now=now)
        if _has(NO_RE, text):
            return self._finish(
                "не очень, значит. хочешь, просто посижу рядом?",
                ["давай поговорим", "расскажи что-нибудь"], now=now)
        return self._finish(
            "слышу тебя. что нового за день?",
            ["всё как обычно", "устал"], now=now)

    def _sleep_reply(self, text, now):
        if _has(NO_RE, text) and not _has(YES_RE, text):
            return self._finish(
                "ладно, ещё пять минут — и спать. телефон правда подождёт.",
                ["спокойной ночи"], now=now)
        return self._finish(
            "спокойной ночи. выспись как следует — завтра всё будет яснее.",
            ["спокойной ночи"], now=now)

    def _stretch_reply(self, text, now):
        if _has(NO_RE, text) and not _has(YES_RE, text):
            return self._finish("ну хоть шею поверни. минута — и хватит.",
                                ["спасибо"], now=now)
        return self._finish("вот и хорошо. спина тебе скажет спасибо)",
                            ["спасибо"], now=now)

    def _followup_reply(self, followup, text, now):
        topic = followup.get("topic")
        state = self._state()
        state["followup"] = {}
        if topic == "meal_food":
            if _has(FOOD_RE, text):
                return {"text": self.rnd.choice([
                    "звучит вкусно) главное — не на бегу.",
                    "одобряю. это лучше, чем ничего.",
                    "хороший выбор. теперь водички ещё.",
                ]), "chips": ["спасибо"], "topic": "meal_food"}
            if text.lower().strip(" .!") in ("не помню", "не знаю", "забыл", "забыла"):
                return {"text": "бывает) главное, что поел.", "chips": [],
                        "topic": "meal_food"}
            return {"text": "поняла. а пил сегодня?", "chips": ["да", "нет"],
                    "topic": "meal_food"}
        if topic == "meal_wait":
            if _has(FOOD_RE, text) or _has(YES_RE, text):
                return {"text": "вот и молодец. я знала, что ты справишься)",
                        "chips": ["спасибо"], "topic": "meal_wait"}
            return None
        return None

