"""Small opt-in live connectivity check; never prints credentials or response bodies."""
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chronos.config import Settings


def main():
    settings = Settings.load()
    if not settings.api_key:
        raise SystemExit("GEMINI_API_KEY is missing")
    payload = {"contents": [{"parts": [{"text": 'Return {"status":"ok"} as JSON.'}]}],
               "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 100}}
    request = Request(f"https://generativelanguage.googleapis.com/v1beta/models/{settings.model}:generateContent",
                      data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": settings.api_key})
    started = time.monotonic()
    try:
        with urlopen(request, timeout=45) as response:
            result = json.load(response)
        print(json.dumps({"ok": bool(result.get("candidates")), "model": settings.model,
                          "seconds": round(time.monotonic() - started, 2), "usage": result.get("usageMetadata", {})}))
    except HTTPError as exc:
        print(json.dumps({"ok": False, "http_status": exc.code, "seconds": round(time.monotonic() - started, 2)}))
        raise SystemExit(1)
    except (URLError, TimeoutError) as exc:
        cause = getattr(exc, "reason", exc)
        print(json.dumps({"ok": False, "error_type": type(cause).__name__, "errno": getattr(cause, "errno", None),
                          "seconds": round(time.monotonic() - started, 2)}))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
