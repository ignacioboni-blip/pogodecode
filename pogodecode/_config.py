"""Tiny persisted-settings helper (remembers the last-used folder)."""

import json
import os

_PATH = os.path.join(os.path.expanduser("~"), ".pogodecode.json")


def load() -> dict:
    try:
        with open(_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save(data: dict) -> None:
    try:
        with open(_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception:
        pass


def last_dir() -> str:
    d = load().get("last_dir", "")
    return d if d and os.path.isdir(d) else ""


def set_last_dir(path: str) -> None:
    data = load()
    data["last_dir"] = os.path.dirname(os.path.abspath(path))
    save(data)
