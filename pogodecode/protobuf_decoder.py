"""Schema-free protobuf wire-format decoder.

Pokemon GO's GAME_MASTER file is a serialized protobuf message. Niantic does
not publish the ``.proto`` schema, and field layouts change with almost every
client update -- which is exactly why schema-bound decoders (the old JSON-era
tools) rot so quickly.

This module decodes the *wire format* directly. It needs no schema, so it keeps
working no matter how Niantic reshuffles their messages. The trade-off is that
fields are identified by their numeric protobuf field number rather than a
human name; the GAME_MASTER layer (see ``gamemaster.py``) recovers the useful
names that are actually present in the file (template IDs).

Wire types handled (see https://protobuf.dev/programming-guides/encoding/):

    0  VARINT          int / bool / enum / signed
    1  I64             fixed64 / sfixed64 / double
    2  LEN             string / bytes / embedded message / packed repeated
    5  I32             fixed32 / sfixed32 / float

Wire types 3 and 4 (start/end group) are legacy and not used by GAME_MASTER;
they raise ``ProtobufDecodeError`` if encountered.
"""

from __future__ import annotations

import base64
import struct
from typing import Any, Dict, List, Optional, Set, Tuple, Union

__all__ = ["ProtobufDecodeError", "decode_message", "try_decode_message", "BYTES_KEY"]

# Non-text binary blobs are emitted as ``{BYTES_KEY: "<base64>"}``. The key
# cannot collide with a real field because decoded field keys are numeric.
BYTES_KEY = "__bytes__"


class ProtobufDecodeError(ValueError):
    """Raised when a byte buffer is not valid protobuf wire format."""


# ---------------------------------------------------------------------------
# Primitive readers
# ---------------------------------------------------------------------------

def _read_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    """Read a base-128 varint. Returns (value, new_pos)."""
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise ProtobufDecodeError("truncated varint")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, pos
        shift += 7
        if shift > 70:  # a varint never needs more than 10 bytes (64 bits)
            raise ProtobufDecodeError("varint too long")


def _looks_like_text(raw: bytes) -> bool:
    """Heuristic: is this length-delimited blob a human-readable string?

    We require valid UTF-8 with no control characters other than common
    whitespace. Empty buffers are treated as text (an empty string).
    """
    if not raw:
        return True
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    for ch in text:
        codepoint = ord(ch)
        if codepoint < 0x20 and ch not in "\t\n\r":
            return False
        if codepoint == 0x7F:
            return False
    return True


# ---------------------------------------------------------------------------
# Message decoding
# ---------------------------------------------------------------------------

# A decoded field value can be a scalar, a nested message (dict), bytes wrapper,
# or a list of any of those when the field repeats.
Decoded = Union[int, float, str, Dict[str, Any], List[Any]]


def _as_bytes(raw: bytes) -> Dict[str, str]:
    return {BYTES_KEY: base64.b64encode(raw).decode("ascii")}


def _decode_length_delimited(
    raw: bytes,
    packed_paths: "Optional[Set[Tuple[int, ...]]]" = None,
    path: "Tuple[int, ...]" = (),
) -> Decoded:
    """Interpret a wire-type-2 payload as message, string, or raw bytes.

    Order of preference:
      1. A nested message, if the bytes parse cleanly *and* consume fully.
      2. A UTF-8 string, if the bytes look like readable text.
      3. Base64-encoded bytes, as a last resort.

    ``packed_paths`` (handled by the caller) lists field paths that are known to
    be *packed repeated scalars* rather than sub-messages -- a distinction the
    wire format cannot otherwise make.
    """
    nested = try_decode_message(raw, packed_paths, path)
    if nested is not None and not _looks_like_text(raw):
        return nested
    if _looks_like_text(raw):
        # A clean message that is also valid text is almost always text
        # (e.g. a template id). Prefer text in that case.
        return raw.decode("utf-8")
    if nested is not None:
        return nested
    return _as_bytes(raw)


def _add_field(out: Dict[str, Any], field_number: int, value: Any) -> None:
    """Insert a field, promoting to a list when a number repeats."""
    key = str(field_number)
    if key in out:
        existing = out[key]
        if isinstance(existing, list):
            existing.append(value)
        else:
            out[key] = [existing, value]
    else:
        out[key] = value


def decode_message(
    buf: bytes,
    packed_paths: "Optional[Set[Tuple[int, ...]]]" = None,
    _path: "Tuple[int, ...]" = (),
) -> Dict[str, Any]:
    """Decode a protobuf message buffer into a ``{field_number: value}`` dict.

    Raises ``ProtobufDecodeError`` on malformed input.

    ``packed_paths`` is an optional set of field paths (tuples of field numbers
    from this message's root) that are *packed repeated scalars*. The wire
    format makes them indistinguishable from sub-messages, so without this hint
    such a field can be silently mis-decoded as a nested message. Listed paths
    are kept as raw ``{__bytes__}`` for the caller to unpack.
    """
    out: Dict[str, Any] = {}
    pos = 0
    n = len(buf)
    while pos < n:
        tag, pos = _read_varint(buf, pos)
        field_number = tag >> 3
        wire_type = tag & 0x07
        if field_number == 0:
            raise ProtobufDecodeError("field number 0 is invalid")

        if wire_type == 0:  # VARINT
            value, pos = _read_varint(buf, pos)
            _add_field(out, field_number, value)
        elif wire_type == 1:  # I64 -> double
            if pos + 8 > n:
                raise ProtobufDecodeError("truncated 64-bit value")
            value = struct.unpack_from("<d", buf, pos)[0]
            pos += 8
            _add_field(out, field_number, value)
        elif wire_type == 2:  # LEN
            length, pos = _read_varint(buf, pos)
            if pos + length > n:
                raise ProtobufDecodeError("length-delimited field overruns buffer")
            raw = buf[pos:pos + length]
            pos += length
            field_path = _path + (field_number,)
            if packed_paths and field_path in packed_paths:
                # Known packed repeated scalar: keep raw, do not recurse.
                _add_field(out, field_number, _as_bytes(raw))
            else:
                _add_field(out, field_number,
                           _decode_length_delimited(raw, packed_paths, field_path))
        elif wire_type == 5:  # I32 -> float
            if pos + 4 > n:
                raise ProtobufDecodeError("truncated 32-bit value")
            value = struct.unpack_from("<f", buf, pos)[0]
            pos += 4
            # float32 only carries ~7 significant digits; trim the float64
            # widening noise (0.342999994... -> 0.343) for readable JSON.
            if value == value and value not in (float("inf"), float("-inf")):
                value = float(f"{value:.7g}")
            _add_field(out, field_number, value)
        else:  # 3, 4 (groups) or 6, 7 (reserved)
            raise ProtobufDecodeError(f"unsupported wire type {wire_type}")
    return out


def try_decode_message(
    buf: bytes,
    packed_paths: "Optional[Set[Tuple[int, ...]]]" = None,
    _path: "Tuple[int, ...]" = (),
) -> Union[Dict[str, Any], None]:
    """Decode ``buf`` as a message, returning ``None`` if it is not valid.

    An empty buffer is not a useful nested message, so it returns ``None``
    (letting the caller treat it as an empty string instead).
    """
    if not buf:
        return None
    try:
        return decode_message(buf, packed_paths, _path)
    except ProtobufDecodeError:
        return None
