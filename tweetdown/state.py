from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


# A packaged EXE keeps its data next to itself, wherever it was launched from.
BASE_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(".")
APP_DIR = BASE_DIR / ".tweetdown"
STATE_PATH = APP_DIR / "state.json"
QUERY_ID_PATH = APP_DIR / "query_ids.json"
SESSION_PATH = APP_DIR / "session.json"


def ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError:
        return default


def save_json(path: Path, payload: Any) -> None:
    ensure_app_dir()
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def load_state() -> dict[str, Any]:
    return load_json(STATE_PATH, {})


def save_state(payload: dict[str, Any]) -> None:
    save_json(STATE_PATH, payload)


def clear_state() -> None:
    try:
        STATE_PATH.unlink()
    except FileNotFoundError:
        pass
