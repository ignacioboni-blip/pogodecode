"""Tests for the Pokédex interpreter layer."""

import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pogodecode.pokedex import Pokedex, _to_signed, _packed_move_ids  # noqa: E402


def _packed_varints(values):
    out = bytearray()
    for v in values:
        while True:
            b = v & 0x7F
            v >>= 7
            if v:
                out.append(b | 0x80)
            else:
                out.append(b)
                break
    return bytes(out)


def test_to_signed_negative_energy():
    # -50 encoded as a 64-bit varint
    assert _to_signed((1 << 64) - 50) == -50
    assert _to_signed(5) == 5


def test_packed_move_ids_from_bytes():
    import base64
    blob = {"__bytes__": base64.b64encode(_packed_varints([214, 221])).decode()}
    assert _packed_move_ids(blob) == [214, 221]


def _make_dex():
    """Build a minimal in-memory Pokédex with one mon and its moves."""
    import base64
    quick = base64.b64encode(_packed_varints([214])).decode()
    charge = base64.b64encode(_packed_varints([90])).decode()
    # CP multiplier table: index 39 must be level 40 (0.7903)
    cpm = [0.0] * 80
    cpm[0] = 0.094
    cpm[39] = 0.7903
    cpm_b64 = base64.b64encode(struct.pack("<80f", *cpm)).decode()

    by_id = {
        "V0001_POKEMON_BULBASAUR": {"2": {
            "1": 1, "4": 12, "5": 4,
            "8": {"1": 128, "2": 118, "3": 111},
            "9": {"__bytes__": quick},
            "10": {"__bytes__": charge},
            "15": 0.7, "16": 6.9,
            "7": {"20": 0.2},
            "26": {"1": 2, "3": 25},
        }},
        "V0214_MOVE_VINE_WHIP_FAST": {"4": {
            "1": 214, "3": 12, "4": 6.0, "12": 500, "15": 5, "11": "vine_whip_fast",
        }},
        "V0090_MOVE_SLUDGE_BOMB": {"4": {
            "1": 90, "3": 4, "4": 85.0, "12": 2500, "15": (1 << 64) - 50,
        }},
        "PLAYER_LEVEL_SETTINGS": {"12": {"3": {"__bytes__": cpm_b64}}},
    }
    return Pokedex(by_id, source="unit")


def test_sheet_core_fields():
    dex = _make_dex()
    s = dex.sheet("V0001_POKEMON_BULBASAUR")
    assert s["name"] == "Bulbasaur"
    assert s["dexNumber"] == 1
    assert s["types"] == ["Grass", "Poison"]
    assert s["baseStats"] == {"attack": 118, "defense": 111, "stamina": 128}
    assert s["baseCaptureRate"] == 0.2
    assert s["evolution"]["candyCost"] == 25


def test_sheet_moves_resolved_with_signed_energy():
    dex = _make_dex()
    s = dex.sheet("V0001_POKEMON_BULBASAUR")
    assert s["fastMoves"][0]["name"] == "Vine Whip"
    assert s["fastMoves"][0]["type"] == "Grass"
    assert s["fastMoves"][0]["energy"] == 5
    assert s["chargeMoves"][0]["name"] == "Sludge Bomb"
    assert s["chargeMoves"][0]["energy"] == -50      # signed


def test_max_cp_level40_matches_reference():
    dex = _make_dex()
    s = dex.sheet("V0001_POKEMON_BULBASAUR")
    assert s["maxCpLevel40"] == 1115     # canonical Bulbasaur max CP


def test_cp_multiplier_indexing():
    dex = _make_dex()
    assert abs(dex.cp_multiplier_for_level(1) - 0.094) < 1e-6
    assert abs(dex.cp_multiplier_for_level(40) - 0.7903) < 1e-6


# -- optional integration against a real file -------------------------------

def _real():
    env = os.environ.get("POGO_GAME_MASTER")
    return env if env and os.path.isfile(env) else None


@pytest.mark.skipif(_real() is None, reason="no real GAME_MASTER file available")
def test_real_file_reference_values():
    from pogodecode.pokedex import load_pokedex
    dex = load_pokedex(_real())
    cases = {
        "V0001_POKEMON_BULBASAUR": (118, 111, 128, 1115),
        "V0006_POKEMON_CHARIZARD": (223, 173, 186, 2889),
        "V0150_POKEMON_MEWTWO": (300, 182, 214, 4178),
    }
    for tid, (atk, dfn, sta, cp) in cases.items():
        s = dex.sheet(tid)
        assert s["baseStats"] == {"attack": atk, "defense": dfn, "stamina": sta}
        assert s["maxCpLevel40"] == cp
