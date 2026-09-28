from html.parser import HTMLParser
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import requests


class _SearchParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results = []
        self._current = None
        self._capture = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a" and "result__a" in attributes.get("class", ""):
            self._current = {"title": "", "url": "", "snippet": ""}
            raw_url = attributes.get("href", "")
            query = parse_qs(urlparse(raw_url).query)
            self._current["url"] = unquote(query.get("uddg", [raw_url])[0])
            self._capture = "title"
        elif tag in {"a", "div"} and self._current and "result__snippet" in attributes.get("class", ""):
            self._capture = "snippet"

    def handle_data(self, data):
        if self._current and self._capture:
            self._current[self._capture] += data

    def handle_endtag(self, tag):
        if tag == "a" and self._current and self._capture == "title":
            self._capture = None
        elif tag == "div" and self._current and self._capture == "snippet":
            self._capture = None
            if self._current["title"] and self._current["snippet"]:
                self.results.append(self._current)
                self._current = None


def search_web(query, limit=5):
    try:
        response = requests.get(
            f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
            headers={"User-Agent": "Jarvis/1.0"},
            timeout=8,
        )
        response.raise_for_status()
        parser = _SearchParser()
        parser.feed(response.text)
        return parser.results[:limit]
    except (requests.RequestException, ValueError):
        return []


def format_search_context(results):
    return "\n".join(
        f"[{index}] {item['title']} ({item['url']})\n{item['snippet']}"
        for index, item in enumerate(results, start=1)
    )