# -*- coding: utf-8 -*-
"""Заглушка Википедии для тестов: сеть не нужна, ответы предсказуемы."""

import json
import urllib.parse


def fake_knowledge_http(url):
    """Имитирует REST summary / search / extracts / DuckDuckGo."""
    if "duckduckgo" in url:
        return json.dumps({"AbstractText": "", "Heading": ""})
    if "/api/rest_v1/page/summary/" in url:
        name = urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace("_", " ")
        return json.dumps({
            "type": "standard",
            "title": name,
            "extract": "%s — это проверенное тестами объяснение. Оно короткое, "
                       "но по делу. И даже с примером." % name,
            "content_urls": {"desktop": {"page": "https://ru.wikipedia.org/wiki/"
                                                  + urllib.parse.quote(name)}},
        })
    if "list=search" in url:
        return json.dumps({"query": {"search": [{"title": "Квантовая физика"}]}})
    if "prop=extracts" in url:
        return json.dumps({"query": {"pages": {"1": {
            "title": "Квантовая физика",
            "extract": "Квантовая физика — раздел физики о микромире. "
                       "Описывает частицы и их состояния.",
        }}}})
    return ""
