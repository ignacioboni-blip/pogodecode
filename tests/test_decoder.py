"""Tests for the schema-free protobuf decoder and GAME_MASTER layer.

The protobuf-level tests build messages by hand so they need no fixtures. If a
real GAME_MASTER file is present (via the POGO_GAME_MASTER env var or a file
named GAME_MASTER in the repo root), an integration test exercises it too.
"""

import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pogodecode.protobuf_decoder import (  # noqa: E402
    BYTES_KEY,
    ProtobufDecodeError,
    decode_message,
)
from pogodecode.gamemaster import decode_game_master  # noqa: E402


# -- tiny protobuf builders -------------------------------------------------

def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def tag(field: int, wire: int) -> bytes:
    return varint((field << 3) | wire)


def field_varint(field: int, value: int) -> bytes:
    return tag(field, 0) + varint(value)


def field_len(field: int, payload: bytes) -> bytes:
    return tag(field, 2) + varint(len(payload)) + payload


def field_string(field: int, text: str) -> bytes:
    return field_len(field, text.encode("utf-8"))


def field_double(field: int, value: float) -> bytes:
    return tag(field, 1) + struct.pack("<d", value)


def field_float(field: int, value: float) -> bytes:
    return tag(field, 5) + struct.pack("<f", value)


# -- protobuf_decoder tests -------------------------------------------------

def test_varint_field():
    assert decode_message(field_varint(1, 150)) == {"1": 150}


def test_string_field():
    assert decode_message(field_string(3, "BULBASAUR")) == {"3": "BULBASAUR"}


def test_double_field_exact():
    assert decode_message(field_double(2, 1.5)) == {"2": 1.5}


def test_float32_noise_is_trimmed():
    # 0.343 stored as float32 widens to 0.34299999... ; we expect it cleaned.
    decoded = decode_message(field_float(4, 0.343))
    assert decoded["4"] == 0.343


def test_repeated_field_becomes_list():
    buf = field_varint(5, 1) + field_varint(5, 2) + field_varint(5, 3)
    assert decode_message(buf) == {"5": [1, 2, 3]}


def test_nested_message():
    inner = field_varint(1, 7) + field_string(2, "hi")
    buf = field_len(10, inner)
    assert decode_message(buf) == {"10": {"1": 7, "2": "hi"}}


def test_non_utf8_becomes_base64_bytes():
    raw = b"\xff\xfe\x00\x01\x02"  # not valid utf-8, not a valid sub-message
    decoded = decode_message(field_len(6, raw))
    assert BYTES_KEY in decoded["6"]


def test_empty_length_field_is_empty_string():
    assert decode_message(field_len(7, b"")) == {"7": ""}


def test_truncated_varint_raises():
    with pytest.raises(ProtobufDecodeError):
        decode_message(b"\x08\x80")  # tag ok, varint never terminates


def test_field_zero_is_invalid():
    with pytest.raises(ProtobufDecodeError):
        decode_message(varint(0 << 3 | 0) + varint(1))


# -- gamemaster layer tests -------------------------------------------------

def _make_template(template_id: str, settings_field: int, settings: bytes) -> bytes:
    data = field_string(1, template_id) + field_len(settings_field, settings)
    template = field_string(1, template_id) + field_len(2, data)
    return field_len(2, template)  # GameMaster.templates


def test_game_master_roundtrip():
    settings = field_varint(1, 42) + field_double(2, 3.14)
    gm = (
        _make_template("POKEMON_SETTINGS_X", 8, settings)
        + _make_template("MOVE_SETTINGS_Y", 9, field_string(1, "TACKLE"))
    )
    result = decode_game_master(gm, source_name="unit")

    assert result["meta"]["templateCount"] == 2
    assert result["meta"]["skippedEntries"] == 0
    assert set(result["templatesById"]) == {"POKEMON_SETTINGS_X", "MOVE_SETTINGS_Y"}

    # redundant template_id (field 1) inside data is dropped
    pokemon = result["templatesById"]["POKEMON_SETTINGS_X"]
    assert "1" not in pokemon
    assert pokemon["8"] == {"1": 42, "2": 3.14}

    # categories are grouped by prefix
    assert "POKEMON" in result["categories"]
    assert "MOVE" in result["categories"]


def test_duplicate_template_ids_are_preserved():
    gm = (
        _make_template("DUP", 3, field_varint(1, 1))
        + _make_template("DUP", 3, field_varint(1, 2))
    )
    result = decode_game_master(gm, source_name="unit")
    assert isinstance(result["templatesById"]["DUP"], list)
    assert len(result["templatesById"]["DUP"]) == 2


def test_garbage_top_level_raises():
    with pytest.raises(ProtobufDecodeError):
        decode_game_master(b"\x1f\x8b\x08not-protobuf", source_name="unit")


# -- optional integration test against a real file --------------------------

def _real_game_master_path():
    env = os.environ.get("POGO_GAME_MASTER")
    if env and os.path.isfile(env):
        return env
    local = os.path.join(os.path.dirname(os.path.dirname(__file__)), "GAME_MASTER")
    return local if os.path.isfile(local) else None


@pytest.mark.skipif(_real_game_master_path() is None, reason="no real GAME_MASTER file available")
def test_real_game_master_decodes():
    result = decode_game_master(_real_game_master_path())
    assert result["meta"]["templateCount"] > 1000
    assert result["meta"]["skippedEntries"] == 0
    # template ids should be plain readable strings
    assert all(isinstance(k, str) and k for k in result["templatesById"])
