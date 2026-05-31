"""Interpret a decoded GAME_MASTER into readable Pokemon / move data sheets.

The :mod:`pogodecode` decoder is intentionally schema-free, so it emits numeric
protobuf field numbers. This module adds the *meaning* on top: a small,
explicitly documented field map (reverse-engineered from a real GAME_MASTER and
checked against known reference values) that turns those numbers into names,
stats, moves and derived values such as max CP.

Everything here is data-driven and easy to amend: if a future client update
shifts a field, edit the constants near the top rather than the logic.

Verified against the file shipped May 2026 (e.g. Bulbasaur Atk 118 / Def 111 /
Sta 128, Grass/Poison; Mewtwo base capture rate 0.02; CP multiplier L40 0.7903).
"""

from __future__ import annotations

import base64
import math
import os
import re
import struct
from typing import Any, Dict, List, Optional

from .gamemaster import decode_game_master

__all__ = ["Pokedex", "load_pokedex"]

# --- enums -----------------------------------------------------------------

# HoloPokemonType enum (POGOProtos). Index == protobuf enum value.
TYPE_NAMES = {
    0: "None", 1: "Normal", 2: "Fighting", 3: "Flying", 4: "Poison",
    5: "Ground", 6: "Rock", 7: "Bug", 8: "Ghost", 9: "Steel", 10: "Fire",
    11: "Water", 12: "Grass", 13: "Electric", 14: "Psychic", 15: "Ice",
    16: "Dragon", 17: "Dark", 18: "Fairy",
}

# --- field map: PokemonSettings (template "data" field 2) ------------------
# Each PokemonSettings message lives under data field "2".
PF_SETTINGS = "2"
PF_DEX_ENUM = "1"        # pokemon id enum
PF_MODEL_SCALE = "3"
PF_TYPE1 = "4"
PF_TYPE2 = "5"
PF_ENCOUNTER = "7"       # sub-message; .20 == base capture rate
PF_ENC_CAPTURE = "20"
PF_STATS = "8"           # {1: stamina, 2: attack, 3: defense}
PF_STAT_STAMINA, PF_STAT_ATTACK, PF_STAT_DEFENSE = "1", "2", "3"
PF_QUICK_MOVES = "9"     # packed varint move ids
PF_CHARGE_MOVES = "10"   # packed varint move ids
PF_HEIGHT_M = "15"
PF_WEIGHT_KG = "16"
PF_EVOLUTION = "26"      # {1: evolves-to id, 3: candy cost, ...}
PF_FORM = "28"
PF_SECOND_MOVE = "36"    # {1: stardust, 2: candy} to unlock 2nd charge move
PF_SHADOW = "46"         # {1: purify stardust, 2: purify candy, 3: purified, 4: shadow move}

# --- field map: MoveSettings (PvE, data field 4) ---------------------------
MF_PVE = "4"
MF_PVE_ID = "1"
MF_PVE_TYPE = "3"
MF_PVE_POWER = "4"
MF_PVE_DURATION = "12"
MF_PVE_ENERGY = "15"
MF_PVE_NAME = "11"
# --- field map: CombatMove (PvP, data field 37) ----------------------------
MF_PVP = "37"
MF_PVP_ID = "1"
MF_PVP_TYPE = "2"
MF_PVP_POWER = "3"
MF_PVP_ENERGY = "5"

# --- field map: PLAYER_LEVEL_SETTINGS (data field 12) ----------------------
PL_SETTINGS = "12"
PL_CP_MULTIPLIER = "3"   # packed float32 array, index 0 == level 1.0
PL_REQUIRED_XP = "2"     # packed varint array

_RE_POKEMON = re.compile(r"^V(\d+)_POKEMON_(.+)$")
_RE_MOVE = re.compile(r"^(?:COMBAT_)?V(\d+)_MOVE_(.+)$")


# --- packed-array helpers --------------------------------------------------

def _unpack_varints(b64: str) -> List[int]:
    raw = base64.b64decode(b64)
    out: List[int] = []
    i = 0
    while i < len(raw):
        shift = val = 0
        while True:
            x = raw[i]
            i += 1
            val |= (x & 0x7F) << shift
            if not (x & 0x80):
                break
            shift += 7
        out.append(val)
    return out


def _unpack_floats(b64: str) -> List[float]:
    raw = base64.b64decode(b64)
    return list(struct.unpack("<%df" % (len(raw) // 4), raw))


def _packed_move_ids(value: Any) -> List[int]:
    """Move id lists are packed varints; the generic decoder leaves them as
    bytes (or, by coincidence, a short string). Recover the integer ids."""
    if value is None:
        return []
    if isinstance(value, dict) and "__bytes__" in value:
        return _unpack_varints(value["__bytes__"])
    if isinstance(value, str):
        # decoder saw printable bytes and returned a str; re-read raw bytes
        ids: List[int] = []
        shift = val = 0
        for ch in value.encode("latin-1", "ignore"):
            val |= (ch & 0x7F) << shift
            if ch & 0x80:
                shift += 7
            else:
                ids.append(val)
                shift = val = 0
        return ids
    if isinstance(value, list):
        return [int(v) for v in value]
    if isinstance(value, int):
        return [value]
    return []


def _to_signed(value: Any) -> Any:
    """Protobuf encodes negative int32/int64 as a 10-byte varint (2**64 + n).
    Move energy *cost* is negative, so recover the signed value."""
    if isinstance(value, int) and value >= (1 << 63):
        return value - (1 << 64)
    return value


def _prettify(token: str) -> str:
    """V0001_POKEMON_BULBASAUR -> 'Bulbasaur'; VINE_WHIP_FAST -> 'Vine Whip'."""
    token = token.replace("_FAST", "")
    return token.replace("_", " ").title()


# --- main object -----------------------------------------------------------

class Move:
    __slots__ = ("id", "name", "raw_name", "type", "type_name", "power",
                 "energy", "duration_ms", "is_fast", "pvp_power", "pvp_energy")

    def __init__(self, move_id: int, raw_name: str) -> None:
        self.id = move_id
        self.raw_name = raw_name
        self.name = _prettify(raw_name)
        self.is_fast = raw_name.endswith("_FAST")
        self.type = 0
        self.type_name = "None"
        self.power = 0.0
        self.energy = 0
        self.duration_ms = 0
        self.pvp_power = None
        self.pvp_energy = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "type": self.type_name,
            "category": "Fast" if self.is_fast else "Charge",
            "power": self.power, "energy": self.energy,
            "durationMs": self.duration_ms,
            "pvpPower": self.pvp_power, "pvpEnergy": self.pvp_energy,
        }


class Pokemon:
    def __init__(self, template_id: str, dex: int, settings: Dict[str, Any]) -> None:
        self.template_id = template_id
        self.dex = dex
        self._settings = settings

    @property
    def name(self) -> str:
        m = _RE_POKEMON.match(self.template_id)
        return _prettify(m.group(2)) if m else self.template_id

    @property
    def form(self) -> Optional[str]:
        m = _RE_POKEMON.match(self.template_id)
        if not m:
            return None
        # the species name is the shortest known token; keep any trailing form
        return m.group(2)

    def _g(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)


class Pokedex:
    """Interpreted view over a decoded GAME_MASTER."""

    def __init__(self, by_id: Dict[str, Any], source: str = "") -> None:
        self._by_id = by_id
        self.source = source
        self.moves: Dict[int, Move] = {}
        self.cp_multipliers: List[float] = []
        self.required_xp: List[int] = []
        self._pokemon_keys: List[str] = []
        self._build()

    # -- construction -------------------------------------------------------
    def _build(self) -> None:
        self._build_moves()
        self._build_levels()
        self._pokemon_keys = sorted(
            (k for k, v in self._by_id.items()
             if _RE_POKEMON.match(k)
             and isinstance(v, dict)
             and isinstance(v.get(PF_SETTINGS), dict)
             and PF_STATS in v[PF_SETTINGS]),
            key=lambda k: (int(_RE_POKEMON.match(k).group(1)), k),
        )

    def _build_moves(self) -> None:
        for tid, data in self._by_id.items():
            m = _RE_MOVE.match(tid)
            if not m or not isinstance(data, dict):
                continue
            move_id = int(m.group(1))
            is_combat = tid.startswith("COMBAT_")
            if not is_combat and MF_PVE in data:
                s = data[MF_PVE]
                mv = self.moves.get(move_id) or Move(move_id, m.group(2))
                mv.type = int(s.get(MF_PVE_TYPE, 0) or 0)
                mv.type_name = TYPE_NAMES.get(mv.type, str(mv.type))
                mv.power = s.get(MF_PVE_POWER, 0.0) or 0.0
                mv.energy = int(_to_signed(s.get(MF_PVE_ENERGY, 0) or 0))
                mv.duration_ms = int(s.get(MF_PVE_DURATION, 0) or 0)
                self.moves[move_id] = mv
            elif is_combat and MF_PVP in data:
                s = data[MF_PVP]
                mv = self.moves.get(move_id) or Move(move_id, m.group(2))
                mv.pvp_power = s.get(MF_PVP_POWER)
                mv.pvp_energy = _to_signed(s.get(MF_PVP_ENERGY)) if s.get(MF_PVP_ENERGY) is not None else None
                self.moves.setdefault(move_id, mv)

    def _build_levels(self) -> None:
        pls = self._by_id.get("PLAYER_LEVEL_SETTINGS")
        if isinstance(pls, dict) and isinstance(pls.get(PL_SETTINGS), dict):
            block = pls[PL_SETTINGS]
            cpm = block.get(PL_CP_MULTIPLIER)
            if isinstance(cpm, dict) and "__bytes__" in cpm:
                self.cp_multipliers = _unpack_floats(cpm["__bytes__"])
            xp = block.get(PL_REQUIRED_XP)
            if isinstance(xp, dict) and "__bytes__" in xp:
                self.required_xp = _unpack_varints(xp["__bytes__"])

    # -- lookups ------------------------------------------------------------
    def pokemon_keys(self) -> List[str]:
        return list(self._pokemon_keys)

    def move_name(self, move_id: int) -> str:
        mv = self.moves.get(move_id)
        return mv.name if mv else f"Move #{move_id}"

    def cp_multiplier_for_level(self, level: float) -> Optional[float]:
        """CP multiplier for a level from the GAME_MASTER table.

        Layout in the file: indices 0..39 are integer levels 1..40; beyond that
        the table steps in half levels (index 39 + 2*(level-40)).
        """
        if 1 <= level <= 40 and float(level).is_integer():
            idx = int(level) - 1
        elif level > 40:
            idx = 39 + int(round((level - 40) / 0.5))
        else:
            return None
        if 0 <= idx < len(self.cp_multipliers):
            return self.cp_multipliers[idx]
        return None

    def max_cp(self, attack: int, defense: int, stamina: int,
               level: float = 40.0, iv: int = 15) -> Optional[int]:
        cpm = self.cp_multiplier_for_level(level)
        if not cpm:
            return None
        a = (attack + iv) * cpm
        d = (defense + iv) * cpm
        s = (stamina + iv) * cpm
        cp = int((a * math.sqrt(d) * math.sqrt(s)) / 10.0)
        return max(cp, 10)

    def sheet(self, template_id: str) -> Dict[str, Any]:
        """Build a readable info sheet for one Pokemon template."""
        data = self._by_id[template_id]
        s = data[PF_SETTINGS]
        stats = s.get(PF_STATS, {})
        atk = int(stats.get(PF_STAT_ATTACK, 0) or 0)
        dfn = int(stats.get(PF_STAT_DEFENSE, 0) or 0)
        sta = int(stats.get(PF_STAT_STAMINA, 0) or 0)

        types = [TYPE_NAMES.get(int(s[t]), str(s[t]))
                 for t in (PF_TYPE1, PF_TYPE2) if t in s and s[t]]

        fast = [self._move_brief(mid) for mid in _packed_move_ids(s.get(PF_QUICK_MOVES))]
        charge = [self._move_brief(mid) for mid in _packed_move_ids(s.get(PF_CHARGE_MOVES))]

        enc = s.get(PF_ENCOUNTER, {})
        capture = enc.get(PF_ENC_CAPTURE) if isinstance(enc, dict) else None

        evo = s.get(PF_EVOLUTION, {})
        second = s.get(PF_SECOND_MOVE, {})
        shadow = s.get(PF_SHADOW, {})

        m = _RE_POKEMON.match(template_id)
        dex = int(m.group(1)) if m else 0

        sheet: Dict[str, Any] = {
            "templateId": template_id,
            "dexNumber": dex,
            "name": _prettify(m.group(2)) if m else template_id,
            "form": s.get(PF_FORM),
            "types": types,
            "baseStats": {"attack": atk, "defense": dfn, "stamina": sta},
            "heightM": s.get(PF_HEIGHT_M),
            "weightKg": s.get(PF_WEIGHT_KG),
            "baseCaptureRate": capture,
            "fastMoves": fast,
            "chargeMoves": charge,
            "maxCpLevel40": self.max_cp(atk, dfn, sta, level=40),
        }
        if isinstance(evo, dict) and evo:
            sheet["evolution"] = {
                "candyCost": evo.get("3"),
                "evolvesToId": evo.get("1"),
            }
        if isinstance(second, dict) and second:
            sheet["secondChargeMove"] = {
                "stardust": second.get("1"), "candy": second.get("2"),
            }
        if isinstance(shadow, dict) and shadow:
            sheet["shadow"] = {
                "purificationStardust": shadow.get("1"),
                "purificationCandy": shadow.get("2"),
            }
        return sheet

    def _move_brief(self, move_id: int) -> Dict[str, Any]:
        mv = self.moves.get(move_id)
        if not mv:
            return {"id": move_id, "name": f"Move #{move_id}"}
        return mv.to_dict()

    def all_sheets(self) -> List[Dict[str, Any]]:
        return [self.sheet(k) for k in self._pokemon_keys]


# --- loading ---------------------------------------------------------------

def load_pokedex(path: str) -> Pokedex:
    """Build a Pokedex from a raw GAME_MASTER file or a decoded JSON file.

    Detects a previously-exported JSON (with a ``templatesById`` key) and uses
    it directly; otherwise decodes the raw protobuf.
    """
    import json

    with open(path, "rb") as fh:
        head = fh.read(64)
    looks_json = head.lstrip()[:1] in (b"{", b"[")

    if looks_json:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        by_id = doc.get("templatesById")
        if by_id is None:
            raise ValueError("JSON file has no 'templatesById' (not a pogodecode export)")
    else:
        by_id = decode_game_master(path)["templatesById"]

    return Pokedex(by_id, source=os.path.basename(path))
