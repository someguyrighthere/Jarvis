import json
import re
from datetime import datetime, timezone
from pathlib import Path


KNOWLEDGE_PATH = Path(__file__).resolve().parent / "knowledge.json"
STOP_WORDS = {
    "about", "after", "again", "also", "because", "could", "from", "have",
    "into", "that", "their", "there", "these", "they", "this", "what", "when",
    "where", "which", "with", "would", "your",
}


def _load():
    try:
        data = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []


def _save(entries):
    KNOWLEDGE_PATH.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def save_knowledge(content, source="user"):
    content = content.strip()
    if not content:
        return False
    entries = _load()
    entries.append({
        "content": content,
        "source": source,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    })
    _save(entries)
    return True


def _terms(text):
    return {
        term for term in re.findall(r"[a-z0-9]{3,}", text.lower())
        if term not in STOP_WORDS
    }


def retrieve_knowledge(query, limit=5):
    query_terms = _terms(query)
    scored = []
    for entry in _load():
        content = entry.get("content", "")
        score = len(query_terms & _terms(content))
        if score:
            scored.append((score, entry))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [entry for _, entry in scored[:limit]]


def format_knowledge(entries):
    return "\n".join(
        f"[{index}] {entry['content']} (saved from {entry.get('source', 'user')})"
        for index, entry in enumerate(entries, start=1)
    )


def clear_knowledge():
    try:
        KNOWLEDGE_PATH.unlink()
    except FileNotFoundError:
        pass