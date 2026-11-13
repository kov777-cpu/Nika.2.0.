# -*- coding: utf-8 -*-
"""Короткие ответы на «что такое …» без перехода в браузер.

Берём первый абзац из Википедии (русской, потом английской) и, если там
пусто, — короткую выжимку DuckDuckGo. Всё через открытые API, без ключей.
http_get можно подменить в тестах, как в weather.py.
"""

import json
import re
import time
import urllib.parse
import urllib.request

RU_API = "https://ru.wikipedia.org/w/api.php"
RU_SUMMARY = "https://ru.wikipedia.org/api/rest_v1/page/summary/"
EN_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/"
DDG_API = "https://api.duckduckgo.com/"

MAX_CHARS = 380
CACHE_SECONDS = 3600

_QUESTION_PREFIX = re.compile(
    r"^(?:а\s+)?(?:что\s+такое|что\s+значит|кто\s+такой|кто\s+такая|кто\s+такие|"
    r"расскажи(?:\s+мне)?\s+(?:о|об|про)|объясни(?:\s+мне)?(?:\s+что\s+такое)?|"
    r"что\s+за|что\s+таков[ао]?|это\s+что)(?:\s+|$)",
    re.IGNORECASE,
)
_TOPIC_JUNK = re.compile(r"[\"'«»„“”`]+")
_TAIL_WORDS = ("пожалуйста", "плиз", "мне", "коротко", "если можешь")


def clean_topic(text):
    """«Что такое квантовая физика?» -> «квантовая физика»."""
    t = (text or "").strip()
    t = _QUESTION_PREFIX.sub("", t, count=1)
    t = _TOPIC_JUNK.sub("", t).strip(" .,!?;:—-")
    words = [w for w in t.split() if w.lower() not in _TAIL_WORDS]
    t = " ".join(words).strip()
    if len(t) < 2:
        return ""
    return t


def _default_http(url):
    context = None
    try:
        import ssl

        context = ssl.create_default_context()
        try:
            import certifi
            context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
    except Exception:
        context = None
    request = urllib.request.Request(url, headers={
        "User-Agent": "Nika/1.1 (Android; +https://example.invalid)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(request, timeout=8, context=context) as response:
        return response.read().decode("utf-8", "replace")


def _shorten(text, limit=MAX_CHARS):
    """Оставляет 2–4 целых предложения, чтобы ответ влез в чат."""
    t = re.sub(r"\s+", " ", text or "").strip()
    if not t:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", t)
    out = []
    total = 0
    for sentence in sentences:
        if not sentence:
            continue
        if out and total + len(sentence) > limit:
            break
        out.append(sentence)
        total += len(sentence) + 1
        if len(out) >= 3:
            break
    result = " ".join(out).strip()
    if len(result) > limit + 80:
        result = result[:limit].rstrip(" ,;:") + "…"
    return result


class Knowledge:
    """Поиск короткого объяснения. Возвращает dict или None."""

    def __init__(self, http_get=None, timeout=8):
        self.http_get = http_get or _default_http
        self.timeout = timeout
        self._cache = {}
        self.last_error = ""

    # ---------- сеть ----------
    def _json(self, url):
        raw = self.http_get(url)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def _summary(self, lang, topic):
        base = RU_SUMMARY if lang == "ru" else EN_SUMMARY
        url = base + urllib.parse.quote(topic.replace(" ", "_"), safe="")
        data = self._json(url)
        if not isinstance(data, dict):
            return None
        if data.get("type") == "disambiguation":
            return None
        extract = data.get("extract") or ""
        title = data.get("title") or topic
        page = ((data.get("content_urls") or {}).get("desktop") or {}).get("page") or ""
        if not extract:
            return None
        return {"title": title, "text": extract, "url": page, "lang": lang}

    def _search_title(self, lang, topic):
        url = (RU_API if lang == "ru" else "https://en.wikipedia.org/w/api.php") + \
            "?action=query&list=search&format=json&utf8=1&srlimit=1&srsearch=" + \
            urllib.parse.quote(topic)
        data = self._json(url)
        try:
            return data["query"]["search"][0]["title"]
        except Exception:
            return ""

    def _extract(self, lang, title):
        url = (RU_API if lang == "ru" else "https://en.wikipedia.org/w/api.php") + \
            "?action=query&prop=extracts&format=json&utf8=1&exintro=1&explaintext=1" \
            "&redirects=1&titles=" + urllib.parse.quote(title)
        data = self._json(url)
        try:
            pages = data["query"]["pages"]
            page = next(iter(pages.values()))
            text = page.get("extract") or ""
            if not text:
                return None
            return {"title": page.get("title") or title, "text": text,
                    "url": "https://%s.wikipedia.org/wiki/%s" % (
                        lang, urllib.parse.quote(title.replace(" ", "_"))),
                    "lang": lang}
        except Exception:
            return None

    def _duckduckgo(self, topic):
        url = DDG_API + "?format=json&no_html=1&skip_disambig=1&q=" + \
            urllib.parse.quote(topic)
        data = self._json(url)
        if not isinstance(data, dict):
            return None
        text = (data.get("AbstractText") or "").strip()
        if not text:
            return None
        return {"title": data.get("Heading") or topic, "text": text,
                "url": data.get("AbstractURL") or "", "lang": "en"}

    def _lookup(self, topic):
        for lang in ("ru", "en"):
            info = self._summary(lang, topic)
            if info:
                return info
            title = self._search_title(lang, topic)
            if title:
                info = self._extract(lang, title) or self._summary(lang, title)
                if info:
                    return info
        return self._duckduckgo(topic)

    # ---------- публичный интерфейс ----------
    def answer(self, question):
        """Возвращает {"text", "title", "url", "lang"} или None."""
        topic = clean_topic(question)
        self.last_error = ""
        if not topic:
            self.last_error = "empty"
            return None

        cached = self._cache.get(topic.lower())
        if cached and time.time() - cached[0] < CACHE_SECONDS:
            return cached[1]

        try:
            info = self._lookup(topic)
        except Exception as exc:  # сеть, таймауты, кривой JSON
            self.last_error = "offline"
            print("[Nika/knowledge] %s" % exc)
            return None

        if not info:
            self.last_error = "empty"
            return None

        text = _shorten(info.get("text"))
        if not text:
            self.last_error = "empty"
            return None
        info = dict(info)
        info["text"] = text
        self._cache[topic.lower()] = (time.time(), info)
        return info
