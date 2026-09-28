import ast
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


PROJECT_ROOT = Path(__file__).resolve().parent
REQUEST_PATH = PROJECT_ROOT / "improvement_request.json"
BACKUP_DIR = PROJECT_ROOT / "self_update_backups"
OLLAMA_ENDPOINT = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/v1/chat/completions")
MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


def _save(payload):
    REQUEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _load():
    try:
        payload = json.loads(REQUEST_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _target_for_request(request):
    request = request.lower()
    if any(word in request for word in ("voice", "speak", "speech", "tts", "formal", "style")):
        return "TextToSpeech/Fast_DF_TTS.py"
    if any(word in request for word in ("remember", "memory", "answer", "personality")):
        return "Brain/brain.py"
    return "co_brain.py"


def create_improvement_proposal(request):
    target = _target_for_request(request)
    source_path = PROJECT_ROOT / target
    try:
        source = source_path.read_text(encoding="utf-8")
    except OSError as error:
        return {"ok": False, "message": f"I could not read {target}: {error}"}

    prompt = (
        "Return only valid JSON with exactly these keys: summary and content. "
        "The content must be the complete replacement Python source file. "
        "Preserve existing behavior unless the requested change requires otherwise. "
        "Do not use shell commands, subprocesses, eval, exec, or modify other files.\n\n"
        f"Requested improvement: {request}\n"
        f"Target file: {target}\n\n"
        f"Current source:\n{source}"
    )
    try:
        response = requests.post(
            OLLAMA_ENDPOINT,
            headers={"Content-Type": "application/json"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 8000,
            },
            timeout=90,
        )
        response.raise_for_status()
        answer = response.json()["choices"][0]["message"]["content"].strip()
        if answer.startswith("```"):
            answer = answer.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        proposal = json.loads(answer)
        content = proposal.get("content")
        summary = proposal.get("summary")
        if not isinstance(content, str) or not isinstance(summary, str):
            raise ValueError("The model returned an incomplete proposal")
        ast.parse(content, filename=str(source_path))
    except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
        return {"ok": False, "message": f"I could not create a safe proposal: {error}"}

    payload = {
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "request": request.strip(),
        "status": "proposed",
        "target": target,
        "summary": summary.strip(),
        "content": content,
    }
    _save(payload)
    return {"ok": True, "message": f"I prepared a proposal for {target}: {summary.strip()}"}


def apply_pending_improvement():
    payload = _load()
    if not payload or payload.get("status") != "proposed":
        return {"ok": False, "message": "There is no proposed improvement waiting for approval."}

    target = payload.get("target", "")
    source_path = (PROJECT_ROOT / target).resolve()
    try:
        source_path.relative_to(PROJECT_ROOT)
        if source_path.suffix != ".py" or not isinstance(payload.get("content"), str):
            raise ValueError("The proposed target is not a Python source file")
        ast.parse(payload["content"], filename=str(source_path))
        original = source_path.read_text(encoding="utf-8")
        BACKUP_DIR.mkdir(exist_ok=True)
        backup_path = BACKUP_DIR / f"{source_path.stem}-{datetime.now().strftime('%Y%m%d%H%M%S')}.py"
        backup_path.write_text(original, encoding="utf-8")
        source_path.write_text(payload["content"], encoding="utf-8")
        payload.update({"status": "applied", "applied_at": datetime.now(timezone.utc).isoformat(), "backup": str(backup_path.name)})
        _save(payload)
        return {"ok": True, "message": f"Applied the approved improvement to {target}. A backup is in {backup_path.name}."}
    except (OSError, ValueError, SyntaxError) as error:
        try:
            if "original" in locals():
                source_path.write_text(original, encoding="utf-8")
        except OSError:
            pass
        return {"ok": False, "message": f"The improvement was rejected and the original file was restored: {error}"}