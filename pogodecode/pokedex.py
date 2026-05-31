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

__all__ = ["Pokedex", "load_pokedex", "diff_pokedex", "diff_files"]

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
PF_BUDDY_KM = "23"       # buddy walked distance (km per candy)
PF_TEMP_EVO = "51"       # repeated temporary-evolution (Mega) overrides
PF_SECOND_MOVE = "36"    # {1: stardust, 2: candy} to unlock 2nd charge move
PF_SHADOW = "46"         # {1: purify stardust, 2: purify candy, 3: purified, 4: shadow move}

# Temp-evolution sub-message fields and the evo-id enum -> readable name.
TE_STATS = "2"           # {1: stamina, 2: attack, 3: defense}
TE_HEIGHT = "3"
TE_WEIGHT = "4"
TE_TYPE1 = "5"
TE_TYPE2 = "6"
TEMP_EVO_NAMES = {1: "Mega", 2: "Mega X", 3: "Mega Y", 4: "Primal"}
# synthetic-key separator used to expose Mega forms as their own list entries
TEMPEVO_SEP = "::TEMPEVO::"

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
_RE_TYPE = re.compile(r"^POKEMON_TYPE_([A-Z]+)$")
_RE_WEATHER = re.compile(r"^WEATHER_AFFINITY_(.+)$")
_RE_ITEM = re.compile(r"^ITEM_(.+)$")
_RE_LEAGUE = re.compile(r"^COMBAT_LEAGUE_(.+)$")
_RE_FRIENDSHIP = re.compile(r"^FRIENDSHIP_LEVEL_(\d+)$")

# Weather affinity: data field 25 = {1: weather id, 2: packed boosted type ids}
WX_SETTINGS = "25"
WX_TYPES = "2"
# Item: data field 3 = {1: item id, 2: category}
IT_SETTINGS = "3"
IT_ID = "1"
IT_CATEGORY = "2"
# Combat league: data field 35; CP cap at 4 -> 2 -> 2
LG_SETTINGS = "35"
LG_TITLE = "1"
LG_BANNED = "7"          # packed pokemon ids excluded/allowed
# Friendship: data field 31 = {1: unlock days, 3: attack bonus multiplier}
FR_SETTINGS = "31"
FR_UNLOCK_DAYS = "1"
FR_ATTACK_BONUS = "3"

# --- field map: POKEMON_TYPE_* (type effectiveness, data field 8) ----------
TY_SETTINGS = "8"
TY_SCALARS = "1"     # packed float32: attack multipliers vs defending types 1..18
TY_TYPE_ID = "2"

# --- field map: POKEMON_UPGRADE_SETTINGS (data field 18) -------------------
PU_SETTINGS = "18"
PU_CANDY = "3"       # packed varint: candy cost per upgrade step
PU_STARDUST = "4"    # packed varint: stardust cost per upgrade step


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

    @property
    def dps(self) -> float:
        """Damage per second (PvE)."""
        return round(self.power / (self.duration_ms / 1000.0), 2) if self.duration_ms else 0.0

    @property
    def eps(self) -> float:
        """Energy per second (PvE); negative for charge moves (energy spent)."""
        return round(self.energy / (self.duration_ms / 1000.0), 2) if self.duration_ms else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "type": self.type_name,
            "category": "Fast" if self.is_fast else "Charge",
            "power": self.power, "energy": self.energy,
            "durationMs": self.duration_ms,
            "dps": self.dps, "eps": self.eps,
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
        self._build_type_chart()
        self._build_upgrade_costs()
        self._build_weather()
        base_keys = [
            k for k, v in self._by_id.items()
            if _RE_POKEMON.match(k)
            and isinstance(v, dict)
            and isinstance(v.get(PF_SETTINGS), dict)
            and PF_STATS in v[PF_SETTINGS]
        ]
        # Expose each Mega / temporary-evolution override as its own entry.
        keys: List[str] = []
        for k in base_keys:
            keys.append(k)
            overrides = self._by_id[k][PF_SETTINGS].get(PF_TEMP_EVO)
            if isinstance(overrides, dict):
                overrides = [overrides]
            if isinstance(overrides, list):
                for ov in overrides:
                    if isinstance(ov, dict) and TE_STATS in ov:
                        keys.append(f"{k}{TEMPEVO_SEP}{ov.get('1', 0)}")
        self._pokemon_keys = sorted(
            keys, key=lambda x: (int(_RE_POKEMON.match(x.split(TEMPEVO_SEP)[0]).group(1)), x)
        )
        # pokemon id enum (settings field 1) -> readable name, for evolution targets
        self._id_to_name: Dict[int, str] = {}
        for k in base_keys:
            pid = self._by_id[k][PF_SETTINGS].get(PF_DEX_ENUM)
            mm = _RE_POKEMON.match(k)
            if isinstance(pid, int) and mm and pid not in self._id_to_name:
                self._id_to_name[pid] = _prettify(mm.group(2))

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

    def _build_type_chart(self) -> None:
        """attacker type id -> [18 attack multipliers vs defending types 1..18]."""
        self.type_chart: Dict[int, List[float]] = {}
        for tid, data in self._by_id.items():
            if not _RE_TYPE.match(tid) or not isinstance(data, dict):
                continue
            blk = data.get(TY_SETTINGS)
            if not isinstance(blk, dict):
                continue
            scalars = blk.get(TY_SCALARS)
            type_id = blk.get(TY_TYPE_ID)
            if isinstance(scalars, dict) and "__bytes__" in scalars and type_id:
                vals = _unpack_floats(scalars["__bytes__"])
                if len(vals) >= 18:
                    self.type_chart[int(type_id)] = vals[:18]

    def _build_weather(self) -> None:
        """weather name -> [boosted type ids]; and reverse type id -> weathers."""
        self.weather_boosts: Dict[str, List[int]] = {}
        self.type_weather: Dict[int, List[str]] = {}
        for tid, data in self._by_id.items():
            m = _RE_WEATHER.match(tid)
            if not m or not isinstance(data, dict):
                continue
            blk = data.get(WX_SETTINGS)
            if not isinstance(blk, dict):
                continue
            name = _prettify(m.group(1))
            type_ids = _packed_move_ids(blk.get(WX_TYPES))
            self.weather_boosts[name] = type_ids
            for t in type_ids:
                self.type_weather.setdefault(t, []).append(name)

    def _build_upgrade_costs(self) -> None:
        self.upgrade_candy: List[int] = []
        self.upgrade_stardust: List[int] = []
        pus = self._by_id.get("POKEMON_UPGRADE_SETTINGS")
        if isinstance(pus, dict) and isinstance(pus.get(PU_SETTINGS), dict):
            blk = pus[PU_SETTINGS]
            candy = blk.get(PU_CANDY)
            dust = blk.get(PU_STARDUST)
            if isinstance(candy, dict) and "__bytes__" in candy:
                self.upgrade_candy = _unpack_varints(candy["__bytes__"])
            if isinstance(dust, dict) and "__bytes__" in dust:
                self.upgrade_stardust = _unpack_varints(dust["__bytes__"])

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

        This array is **integer-level indexed**: ``index = level - 1``. So L40 is
        index 39 (0.7903) and L50 is index 49 (0.8403); L51-L55 (best-buddy boost)
        continue at indices 50-54, then the table is padded flat at 0.8653.

        NOTE: a frequent bug is assuming half-level steps after L40 (index =
        39 + 2*(level-40)); that lands on the padded 0.8653 cap and overstates
        Level-50 CP by ~6%. Integer indexing here matches the in-game values.
        """
        if level < 1:
            return None
        idx = int(round(level - 1))
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

    # -- type effectiveness -------------------------------------------------
    def type_matchups(self, defending_type_ids: List[int]) -> Dict[str, Any]:
        """Combine attack multipliers across a defender's type(s).

        Returns weaknesses (multiplier > 1) and resistances (< 1), each as a
        list of ``{"type": name, "multiplier": x}`` sorted by impact.
        """
        weak: List[Dict[str, Any]] = []
        resist: List[Dict[str, Any]] = []
        for attacker in range(1, 19):
            row = self.type_chart.get(attacker)
            if not row:
                continue
            mult = 1.0
            for dt in defending_type_ids:
                if 1 <= dt <= 18:
                    mult *= row[dt - 1]
            entry = {"type": TYPE_NAMES[attacker], "multiplier": round(mult, 4)}
            if mult > 1.01:
                weak.append(entry)
            elif mult < 0.99:
                resist.append(entry)
        weak.sort(key=lambda e: -e["multiplier"])
        resist.sort(key=lambda e: e["multiplier"])
        return {"weakTo": weak, "resistantTo": resist}

    def type_chart_named(self) -> Dict[str, Dict[str, float]]:
        """Full chart as {attacker name: {defender name: multiplier}}."""
        out: Dict[str, Dict[str, float]] = {}
        for attacker, row in sorted(self.type_chart.items()):
            out[TYPE_NAMES[attacker]] = {
                TYPE_NAMES[d + 1]: round(row[d], 4) for d in range(18)
            }
        return out

    # -- power-up costs -----------------------------------------------------
    def power_up_summary(self) -> Dict[str, Any]:
        """Total candy/stardust to fully power up (constant for all species)."""
        return {
            "steps": max(len(self.upgrade_candy), len(self.upgrade_stardust)),
            "totalCandy": sum(self.upgrade_candy),
            "totalStardust": sum(self.upgrade_stardust),
            "candyPerStep": self.upgrade_candy,
            "stardustPerStep": self.upgrade_stardust,
        }

    def cp_table(self, attack: int, defense: int, stamina: int,
                 iv: int = 15, levels: Optional[List[float]] = None) -> List[Dict[str, Any]]:
        """CP at a set of levels (default 10..50 step 5) for the given stats."""
        if levels is None:
            levels = [float(x) for x in (10, 15, 20, 25, 30, 35, 40, 45, 50)]
        rows = []
        for lv in levels:
            cp = self.max_cp(attack, defense, stamina, level=lv, iv=iv)
            if cp is not None:
                rows.append({"level": lv, "cp": cp})
        return rows

    # -- moves browser ------------------------------------------------------
    def all_moves(self) -> List[Dict[str, Any]]:
        return [self.moves[mid].to_dict() for mid in sorted(self.moves)]

    # -- validation ---------------------------------------------------------
    def validate(self) -> Dict[str, Any]:
        """Sanity-check the decoded data; report anomalies for verification."""
        no_fast, no_charge, stat_outliers, bad_types = [], [], [], []
        unresolved: Dict[int, int] = {}
        zero_duration_moves: List[str] = []

        for key in self._pokemon_keys:
            if TEMPEVO_SEP in key:
                continue
            s = self._by_id[key][PF_SETTINGS]
            fast_ids = _packed_move_ids(s.get(PF_QUICK_MOVES))
            charge_ids = _packed_move_ids(s.get(PF_CHARGE_MOVES))
            if not fast_ids:
                no_fast.append(key)
            if not charge_ids:
                no_charge.append(key)
            for mid in fast_ids + charge_ids:
                if mid not in self.moves:
                    unresolved[mid] = unresolved.get(mid, 0) + 1
            st = s.get(PF_STATS, {})
            for v in (st.get(PF_STAT_ATTACK), st.get(PF_STAT_DEFENSE), st.get(PF_STAT_STAMINA)):
                if not isinstance(v, int) or v <= 0 or v > 600:
                    stat_outliers.append(key)
                    break
            for t in (PF_TYPE1, PF_TYPE2):
                if t in s and s[t] and not (1 <= int(s[t]) <= 18):
                    bad_types.append(key)
                    break

        for mv in self.moves.values():
            if mv.duration_ms <= 0:
                zero_duration_moves.append(mv.name)

        def sample(seq, n=15):
            seq = list(seq)
            return {"count": len(seq), "sample": seq[:n]}

        return {
            "source": self.source,
            "pokemonChecked": sum(1 for k in self._pokemon_keys if TEMPEVO_SEP not in k),
            "movesChecked": len(self.moves),
            "pokemonWithoutFastMove": sample(no_fast),
            "pokemonWithoutChargeMove": sample(no_charge),
            "unresolvedMoveIds": {"count": len(unresolved),
                                  "sample": dict(list(unresolved.items())[:15])},
            "statOutliers": sample(stat_outliers),
            "invalidTypes": sample(bad_types),
            "movesWithZeroDuration": sample(zero_duration_moves),
            "typeChartAttackers": len(self.type_chart),
            "cpMultiplierLevels": len(self.cp_multipliers),
        }

    # -- items / leagues / friendship / weather -----------------------------
    def items(self) -> List[Dict[str, Any]]:
        out = []
        for tid, data in self._by_id.items():
            m = _RE_ITEM.match(tid)
            if not m or not isinstance(data, dict) or not isinstance(data.get(IT_SETTINGS), dict):
                continue
            s = data[IT_SETTINGS]
            out.append({
                "name": _prettify(m.group(1)),
                "templateId": tid,
                "itemId": s.get(IT_ID),
                "category": s.get(IT_CATEGORY),
            })
        return sorted(out, key=lambda r: (r["itemId"] is None, r["itemId"] or 0))

    def leagues(self) -> List[Dict[str, Any]]:
        out = []
        for tid, data in self._by_id.items():
            m = _RE_LEAGUE.match(tid)
            if not m or not isinstance(data, dict) or not isinstance(data.get(LG_SETTINGS), dict):
                continue
            s = data[LG_SETTINGS]
            cap = None
            cond = s.get("4")
            if isinstance(cond, dict) and isinstance(cond.get("2"), dict):
                cap = cond["2"].get("2")
            out.append({
                "name": _prettify(m.group(1)),
                "templateId": tid,
                "title": s.get(LG_TITLE),
                "cpCap": cap,
                "restrictedCount": len(_packed_move_ids(s.get(LG_BANNED))),
            })
        return sorted(out, key=lambda r: r["name"])

    def friendship_levels(self) -> List[Dict[str, Any]]:
        out = []
        for tid, data in self._by_id.items():
            m = _RE_FRIENDSHIP.match(tid)
            if not m or not isinstance(data, dict) or not isinstance(data.get(FR_SETTINGS), dict):
                continue
            s = data[FR_SETTINGS]
            out.append({
                "level": int(m.group(1)),
                "unlockDays": s.get(FR_UNLOCK_DAYS),
                "attackBonusMultiplier": s.get(FR_ATTACK_BONUS),
            })
        return sorted(out, key=lambda r: r["level"])

    def weather_summary(self) -> Dict[str, List[str]]:
        return {w: [TYPE_NAMES.get(t, str(t)) for t in ts]
                for w, ts in sorted(self.weather_boosts.items())}

    # -- generic template access -------------------------------------------
    def template_ids(self) -> List[str]:
        return sorted(self._by_id)

    def template(self, template_id: str) -> Any:
        return self._by_id.get(template_id)

    def search_templates(self, term: str, limit: int = 500) -> List[str]:
        term = term.lower()
        return [tid for tid in sorted(self._by_id) if term in tid.lower()][:limit]

    def _temp_evo_override(self, settings: Dict[str, Any], evo_id: int) -> Optional[Dict[str, Any]]:
        ov = settings.get(PF_TEMP_EVO)
        if isinstance(ov, dict):
            ov = [ov]
        if isinstance(ov, list):
            for entry in ov:
                if isinstance(entry, dict) and int(entry.get("1", 0) or 0) == evo_id:
                    return entry
        return None

    def list_label(self, key: str) -> str:
        """Human label for a (possibly Mega) entry, used by the list UI."""
        base, _, evo = key.partition(TEMPEVO_SEP)
        m = _RE_POKEMON.match(base)
        name = _prettify(m.group(2)) if m else base
        dex = int(m.group(1)) if m else 0
        if evo:
            name = f"{TEMP_EVO_NAMES.get(int(evo), 'Mega')} {name}"
        return f"#{dex:04d}  {name}"

    def sheet(self, template_id: str) -> Dict[str, Any]:
        """Build a readable info sheet for one Pokemon entry.

        ``template_id`` may carry a Mega/temp-evolution suffix
        (``<base>::TEMPEVO::<id>``), in which case overridden stats and typing
        are applied on top of the base species data.
        """
        base_id, _, evo_token = template_id.partition(TEMPEVO_SEP)
        data = self._by_id[base_id]
        s = data[PF_SETTINGS]

        override = self._temp_evo_override(s, int(evo_token)) if evo_token else None
        ov_stats = override.get(TE_STATS, {}) if override else {}

        stats = s.get(PF_STATS, {})
        atk = int((ov_stats.get(PF_STAT_ATTACK) if override else None) or stats.get(PF_STAT_ATTACK, 0) or 0)
        dfn = int((ov_stats.get(PF_STAT_DEFENSE) if override else None) or stats.get(PF_STAT_DEFENSE, 0) or 0)
        sta = int((ov_stats.get(PF_STAT_STAMINA) if override else None) or stats.get(PF_STAT_STAMINA, 0) or 0)

        if override:
            type_src = {PF_TYPE1: override.get(TE_TYPE1), PF_TYPE2: override.get(TE_TYPE2)}
            height = override.get(TE_HEIGHT, s.get(PF_HEIGHT_M))
            weight = override.get(TE_WEIGHT, s.get(PF_WEIGHT_KG))
        else:
            type_src = s
            height = s.get(PF_HEIGHT_M)
            weight = s.get(PF_WEIGHT_KG)
        type_ids = [int(type_src[t]) for t in (PF_TYPE1, PF_TYPE2) if type_src.get(t)]
        types = [TYPE_NAMES.get(t, str(t)) for t in type_ids]
        matchups = self.type_matchups(type_ids) if self.type_chart else None

        # Mega forms use the base species movepool.
        fast = [self._move_brief(mid) for mid in _packed_move_ids(s.get(PF_QUICK_MOVES))]
        charge = [self._move_brief(mid) for mid in _packed_move_ids(s.get(PF_CHARGE_MOVES))]

        enc = s.get(PF_ENCOUNTER, {})
        capture = enc.get(PF_ENC_CAPTURE) if isinstance(enc, dict) else None

        evo = s.get(PF_EVOLUTION, {})
        second = s.get(PF_SECOND_MOVE, {})
        shadow = s.get(PF_SHADOW, {})

        m = _RE_POKEMON.match(base_id)
        dex = int(m.group(1)) if m else 0
        name = _prettify(m.group(2)) if m else base_id
        if override:
            name = f"{TEMP_EVO_NAMES.get(int(evo_token), 'Mega')} {name}"

        sheet: Dict[str, Any] = {
            "templateId": template_id,
            "dexNumber": dex,
            "name": name,
            "form": s.get(PF_FORM),
            "isMega": bool(override),
            "types": types,
            "weakTo": [e["type"] for e in matchups["weakTo"]] if matchups else [],
            "resistantTo": [e["type"] for e in matchups["resistantTo"]] if matchups else [],
            "baseStats": {"attack": atk, "defense": dfn, "stamina": sta},
            "heightM": height,
            "weightKg": weight,
            "buddyDistanceKm": s.get(PF_BUDDY_KM),
            "boostedWeather": sorted({w for t in type_ids for w in self.type_weather.get(t, [])}),
            "baseCaptureRate": capture,
            "fastMoves": fast,
            "chargeMoves": charge,
            "maxCpLevel40": self.max_cp(atk, dfn, sta, level=40),
            "maxCpLevel50": self.max_cp(atk, dfn, sta, level=50),
            "maxCpLevel51BestBuddy": self.max_cp(atk, dfn, sta, level=51),
        }
        if override:
            return sheet
        branches = evo if isinstance(evo, list) else ([evo] if isinstance(evo, dict) and evo else [])
        evo_list = []
        for br in branches:
            if not isinstance(br, dict):
                continue
            target_id = br.get("1")
            evo_list.append({
                "candyCost": br.get("3"),
                "evolvesTo": self._id_to_name.get(target_id) if isinstance(target_id, int) else None,
                "evolvesToId": target_id,
            })
        if evo_list:
            sheet["evolution"] = evo_list
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


# --- diff ------------------------------------------------------------------

def diff_pokedex(old: "Pokedex", new: "Pokedex") -> Dict[str, Any]:
    """Compare two Pokédex builds and report what changed between updates.

    Reports template add/remove counts, and per-Pokémon changes to the fields a
    verifier usually cares about (stats, typing, moves, max CP, capture rate).
    """
    old_ids, new_ids = set(old.template_ids()), set(new.template_ids())
    added = sorted(new_ids - old_ids)
    removed = sorted(old_ids - new_ids)

    tracked = ("name", "types", "baseStats", "maxCpLevel40", "baseCaptureRate",
               "buddyDistanceKm")
    changes: List[Dict[str, Any]] = []
    common = [k for k in new.pokemon_keys() if k in set(old.pokemon_keys())]
    for key in common:
        a, b = old.sheet(key), new.sheet(key)
        diffs = {}
        for f in tracked:
            if a.get(f) != b.get(f):
                diffs[f] = {"old": a.get(f), "new": b.get(f)}
        am = sorted(m["name"] for m in a["fastMoves"] + a["chargeMoves"])
        bm = sorted(m["name"] for m in b["fastMoves"] + b["chargeMoves"])
        if am != bm:
            diffs["moves"] = {"added": sorted(set(bm) - set(am)),
                              "removed": sorted(set(am) - set(bm))}
        if diffs:
            changes.append({"templateId": key, "name": b["name"], "changes": diffs})

    return {
        "old": old.source, "new": new.source,
        "templatesAdded": {"count": len(added), "sample": added[:25]},
        "templatesRemoved": {"count": len(removed), "sample": removed[:25]},
        "pokemonChanged": {"count": len(changes), "details": changes[:200]},
    }


def diff_files(old_path: str, new_path: str) -> Dict[str, Any]:
    """Convenience: load two GAME_MASTER files (or JSON exports) and diff them."""
    return diff_pokedex(load_pokedex(old_path), load_pokedex(new_path))
