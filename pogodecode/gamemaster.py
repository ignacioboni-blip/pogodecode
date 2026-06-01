"""Decode a Pokemon GO GAME_MASTER file into a usable JSON structure.

The GAME_MASTER binary is a single protobuf message shaped roughly like::

    GameMaster {
        repeated Template templates = 2;   // ~18k entries
    }
    Template {
        string  template_id = 1;           // e.g. "POKEMON_HOME_FORMS_SETTINGS"
        Data    data         = 2;
    }
    Data {
        string  template_id = 1;           // duplicate of Template.template_id
        <oneof> settings     = N;          // payload under a per-type field number
    }

We can read every ``template_id`` directly (they are plain strings in the file),
which is the genuinely useful, stable information. The settings payload under
each template is decoded schema-free via :mod:`protobuf_decoder`, so the tool
keeps working across client updates.
"""

from __future__ import annotations

import datetime
import os
import re
from typing import Any, Dict, List, Optional

from . import protobuf_decoder as pb
from .protobuf_decoder import ProtobufDecodeError, _read_varint

__all__ = ["decode_game_master", "DecodeResult"]

# Field numbers inside the GAME_MASTER layout.
_F_TEMPLATES = 2      # GameMaster.templates
_F_TEMPLATE_ID = 1    # Template.template_id / Data.template_id
_F_DATA = 2           # Template.data

# A Pokemon template id, e.g. "V0150_POKEMON_MEWTWO".
_RE_POKEMON_TID = re.compile(r"^V\d+_POKEMON_")

# Within a Pokemon template, the movepool fields are *packed repeated varints*
# (move ids). On the wire that is indistinguishable from a sub-message, so the
# schema-free decoder can mis-read them; hint the paths so the raw bytes survive
# for the Pokedex layer to unpack. Path is relative to the Template message:
#   Template.data(2) -> PokemonSettings(2) -> quick(9)/charge(10)/elite(49,50)
# Field 77 is Rayquaza's Mega-required move (Dragon Ascent). Field 63 is the
# form-change settings; its move ids live at 63 -> 8 -> 2 -> {1,2} (e.g. Zacian
# Behemoth Blade, Necrozma Sunsteel Strike).
_POKEMON_PACKED_PATHS = {
    (_F_DATA, 2, 9), (_F_DATA, 2, 10), (_F_DATA, 2, 49), (_F_DATA, 2, 50),
    (_F_DATA, 2, 77),
    (_F_DATA, 2, 63, 8, 2, 1), (_F_DATA, 2, 63, 8, 2, 2),
}


class DecodeResult(dict):
    """The decoded GAME_MASTER. A plain dict, ready for ``json.dump``."""


def _iter_top_level_templates(buf: bytes):
    """Yield raw bytes for each top-level template entry (field 2, wire type 2).

    Implemented as a tight, allocation-light scan because the top level holds
    ~18k entries and we only care about field 2.
    """
    pos = 0
    n = len(buf)
    while pos < n:
        tag, pos = _read_varint(buf, pos)
        field_number = tag >> 3
        wire_type = tag & 0x07
        if wire_type == 0:
            _, pos = _read_varint(buf, pos)
        elif wire_type == 1:
            pos += 8
        elif wire_type == 5:
            pos += 4
        elif wire_type == 2:
            length, pos = _read_varint(buf, pos)
            chunk = buf[pos:pos + length]
            pos += length
            if field_number == _F_TEMPLATES:
                yield chunk
        else:
            raise ProtobufDecodeError(
                f"unexpected wire type {wire_type} at top level (not a GAME_MASTER file?)"
            )


def _parse_template(chunk: bytes) -> Optional[Dict[str, Any]]:
    """Parse one Template entry into ``{templateId, data}``."""
    msg = pb.decode_message(chunk)
    template_id = msg.get(str(_F_TEMPLATE_ID))

    if not isinstance(template_id, str):
        # Not the shape we expect; skip rather than crash the whole file.
        return None

    # Pokemon movepools are packed varints that can mis-decode as sub-messages;
    # re-decode this template with the schema hint so they survive as raw bytes.
    if _RE_POKEMON_TID.match(template_id):
        msg = pb.decode_message(chunk, packed_paths=_POKEMON_PACKED_PATHS)
    raw_data = msg.get(str(_F_DATA))

    data: Any = {}
    if isinstance(raw_data, dict):
        # Drop the redundant template_id that Niantic repeats inside Data.
        data = {
            k: v
            for k, v in raw_data.items()
            if not (k == str(_F_TEMPLATE_ID) and v == template_id)
        }
    elif raw_data is not None:
        data = raw_data

    return {"templateId": template_id, "data": data}


def _category_of(template_id: str) -> str:
    """Best-effort grouping key derived from the template id prefix."""
    head = template_id.split("_", 1)[0]
    return head.upper() if head else "OTHER"


def decode_game_master(
    path_or_bytes,
    source_name: Optional[str] = None,
) -> DecodeResult:
    """Decode a GAME_MASTER file (path or raw bytes) into a JSON-ready dict.

    The result has the shape::

        {
          "meta": {...},
          "templatesById": { "<templateId>": <data>, ... },
          "templates":     [ {"templateId": ..., "data": ...}, ... ],
          "categories":    { "POKEMON": [...templateIds...], ... }
        }

    ``templatesById`` is the quick-lookup API surface; ``templates`` preserves
    file order and is safe even when (rarely) a template id repeats.
    """
    if isinstance(path_or_bytes, (bytes, bytearray)):
        buf = bytes(path_or_bytes)
        if source_name is None:
            source_name = "<bytes>"
    else:
        with open(path_or_bytes, "rb") as fh:
            buf = fh.read()
        if source_name is None:
            source_name = os.path.basename(path_or_bytes)

    templates: List[Dict[str, Any]] = []
    by_id: Dict[str, Any] = {}
    categories: Dict[str, List[str]] = {}
    skipped = 0

    for chunk in _iter_top_level_templates(buf):
        try:
            parsed = _parse_template(chunk)
        except ProtobufDecodeError:
            skipped += 1
            continue
        if parsed is None:
            skipped += 1
            continue

        templates.append(parsed)
        tid = parsed["templateId"]
        # On a duplicate id, keep entries as a list so nothing is lost.
        if tid in by_id:
            existing = by_id[tid]
            if isinstance(existing, list):
                existing.append(parsed["data"])
            else:
                by_id[tid] = [existing, parsed["data"]]
        else:
            by_id[tid] = parsed["data"]
        categories.setdefault(_category_of(tid), []).append(tid)

    result = DecodeResult()
    result["meta"] = {
        "source": source_name,
        "sizeBytes": len(buf),
        "templateCount": len(templates),
        "skippedEntries": skipped,
        "categoryCount": len(categories),
        "decodedAt": datetime.datetime.now(datetime.timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "decoder": "pogodecode (schema-free protobuf)",
        "note": (
            "Settings payloads use numeric protobuf field numbers as keys "
            "because Niantic does not publish field names. Template ids are "
            "exact. Binary blobs are wrapped as {\"__bytes__\": <base64>}."
        ),
    }
    result["templatesById"] = by_id
    result["templates"] = templates
    result["categories"] = {k: categories[k] for k in sorted(categories)}
    return result
