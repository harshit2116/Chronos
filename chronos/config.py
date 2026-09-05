"""Server-only configuration. Never serialize Settings into a response."""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default="", repr=False)
    model: str = "gemini-3.5-flash-lite"
    fast_model: str = "gemini-3.5-flash-lite"
    reasoning_model: str = "gemini-3.5-flash"
    grounded_model: str = "gemini-2.5-flash"

    @classmethod
    def load(cls, path: Path | None = None):
        values = {}
        path = path or ROOT / ".env"
        if path.exists():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip().strip('\"').strip("'")
        def get(key, default):
            return os.environ.get(key, values.get(key, default))
        settings = cls(get("GEMINI_API_KEY", ""), get("GEMINI_MODEL", cls.model),
                       get("GEMINI_FAST_MODEL", cls.fast_model),
                       get("GEMINI_REASONING_MODEL", cls.reasoning_model),
                       get("GEMINI_GROUNDED_MODEL", cls.grounded_model))
        for model in (settings.model, settings.fast_model, settings.reasoning_model, settings.grounded_model):
            if not re.fullmatch(r"[a-zA-Z0-9._-]+", model):
                raise ValueError("Invalid model identifier in configuration")
        return settings
