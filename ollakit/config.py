"""Config for ollakit: ~/.config/ollakit/config.json, created on first use."""

import json
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "ollakit" / "config.json"

_DEFAULTS = {
    "chat_model": None,   # picked on first run from installed models
    "embed_model": None,  # picked on first run; prompts for pull if absent
    "notes_dir": None,    # default --index dir for `ollakit ask`
}

_CACHE_DIR = Path.home() / ".cache" / "ollakit"


def load() -> dict:
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text())
    else:
        data = {}
    cfg = {**_DEFAULTS, **data}
    return cfg


def save(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")


def cache_dir() -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR
