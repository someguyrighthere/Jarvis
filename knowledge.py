import json
import logging
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from local_storage import LEGACY_DATA_ROOT, LOCAL_DATA_DIR

KNOWLEDGE_PATH = LOCAL_DATA_DIR / "knowledge.json"
LEGACY_KNOWLEDGE_PATH = LEGACY_DATA_ROOT / "knowledge.json"
LOGGER = logging.getLogger(__name__)
STOP_WORDS = {
    "about", "after", "again", "also", "because", "could", "from", "have",
    "into", "that", "their", "there", "these", "they", "this", "what", "when",
    "where", "which", "with", "would", "your",
}


def _load():
    if not KNOWLEDGE_PATH.exists() and LEGACY_KNOWLEDGE_PATH != KNOWLEDGE_PATH and LEGACY_KNOWLEDGE_PATH.is_file():
        try:
            legacy_data = json.loads(LEGACY_KNOWLEDGE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            LOGGER.exception("Could not migrate SARA's existing knowledge")
            raise
        if not isinstance(legacy_data, list):
            raise ValueError("SARA's existing knowledge must contain a JSON list.")
        _save(legacy_data)
    try:
        data = json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError):
        LOGGER.exception("Could not read SARA's saved knowledge")
        raise
    if not isinstance(data, list):
        raise ValueError("SARA's saved knowledge must contain a JSON list.")
    return data


def _save(entries):
    temporary = None
    try:
        KNOWLEDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=KNOWLEDGE_PATH.parent,
            prefix=f"{KNOWLEDGE_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary = Path(file.name)
            json.dump(entries, file, indent=2, ensure_ascii=False)
            file.flush()
        temporary.replace(KNOWLEDGE_PATH)
    except OSError:
        LOGGER.exception("Could not save SARA's local knowledge")
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


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
    _save([])