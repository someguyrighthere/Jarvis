import json
import os
from datetime import datetime, timezone

REQUEST_PATH = os.path.join(os.path.dirname(__file__), "improvement_request.json")


def save_improvement_request(request):
    payload = {
        "requested_at": datetime.now(timezone.utc).isoformat(),
        "request": request.strip(),
        "status": "needs_review",
        "note": "Review this request before changing source code.",
    }
    with open(REQUEST_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)
    return payload
