import json
import threading
from pathlib import Path
from typing import Optional

from discord_mcp.config import settings

_LOCK = threading.Lock()


def _settings_path() -> Path:
    return settings.project_root / "data" / "guild_settings.json"


def _load() -> dict[str, dict[str, str]]:
    path = _settings_path()
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict[str, dict[str, str]]) -> None:
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_default_role_id(guild_id: str) -> Optional[str]:
    """Role ID auto-assigned to new members of a guild, or None if unset."""
    with _LOCK:
        data = _load()
    return data.get(guild_id, {}).get("default_role_id")


def set_default_role_id(guild_id: str, role_id: Optional[str]) -> None:
    """Set (or clear, with role_id=None) the auto-assign role for a guild."""
    with _LOCK:
        data = _load()
        if role_id is None:
            data.pop(guild_id, None)
        else:
            data.setdefault(guild_id, {})["default_role_id"] = role_id
        _save(data)
