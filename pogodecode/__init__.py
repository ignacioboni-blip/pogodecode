"""pogodecode -- a schema-free Pokemon GO GAME_MASTER decoder.

Public API::

    from pogodecode import decode_game_master, write_json

    result = decode_game_master("GAME_MASTER")
    write_json(result, "game_master.json")
"""

from __future__ import annotations

import json
from typing import Any

from .gamemaster import DecodeResult, decode_game_master
from .protobuf_decoder import ProtobufDecodeError, decode_message

__version__ = "1.1.0"

__all__ = [
    "decode_game_master",
    "DecodeResult",
    "decode_message",
    "ProtobufDecodeError",
    "write_json",
    "dumps_json",
    "__version__",
]


def dumps_json(result: Any, *, pretty: bool = True) -> str:
    """Serialize a decode result to a JSON string."""
    if pretty:
        return json.dumps(result, indent=2, ensure_ascii=False, sort_keys=False)
    return json.dumps(result, separators=(",", ":"), ensure_ascii=False)


def write_json(result: Any, path: str, *, pretty: bool = True) -> None:
    """Write a decode result to ``path`` as UTF-8 JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dumps_json(result, pretty=pretty))
