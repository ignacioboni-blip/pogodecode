"""Tests for the Pokédex interpreter layer."""

import os
import struct
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pogodecode.pokedex import (  # noqa: E402
    Pokedex, Move, _to_signed, _packed_move_ids, diff_to_markdown,
)


def test_bundled_fonts_present_and_theme_imports_headlessly():
    """The UI fonts must ship with the package and the theme module must import
    without Tk (so the CLI/library stay headless-safe)."""
    import glob
    import os
    from pogodecode import _theme  # must not import tkinter at module load
    d = _theme._font_dir()
    ttfs = {os.path.basename(p) for p in glob.glob(os.path.join(d, "*.ttf"))}
    assert "GoogleSansFlex.ttf" in ttfs
    assert any(n.startswith("Quicksand") for n in ttfs)
    # OFL license texts must travel with the fonts.
    assert glob.glob(os.path.join(d, "OFL-*.txt"))
    assert _theme.UI_FONT == "Google Sans Flex"
    assert set(_theme.PALETTES) == {"light", "dark"}


def test_sentinel_power_moves_flagged_as_placeholder():
    """Niantic ships OHKO moves (Horn Drill 9000, Fissure 9001) with a sentinel
    power; they must be flagged, not shown as real moves. No fixture needed."""
    horn = Move(328, "V0328_MOVE_HORN_DRILL"); horn.power = 9000.0
    normal = Move(103, "V0103_MOVE_FIRE_BLAST"); normal.power = 140.0
    assert horn.placeholder is True
    assert horn.to_dict()["placeholder"] is True
    assert normal.placeholder is False
    assert normal.to_dict()["placeholder"] is False


def test_diff_to_markdown_renders_changes():
    """Changelog rendering needs no GAME_MASTER fixture."""
    report = {
        "old": "OLD", "new": "NEW",
        "templatesAdded": {"count": 1, "sample": ["V9999_POKEMON_NEWMON"]},
        "templatesRemoved": {"count": 0, "sample": []},
        "pokemonChanged": {"count": 1, "details": [
            {"templateId": "V0006_POKEMON_CHARIZARD", "name": "Charizard",
             "changes": {"baseStats": {"old": {"attack": 223}, "new": {"attack": 230}},
                         "moves": {"added": ["Fly"], "removed": []}}},
        ]},
    }
    md = diff_to_markdown(report)
    assert "OLD" in md and "NEW" in md
    assert "V9999_POKEMON_NEWMON" in md
    assert "Charizard" in md
    assert "moves +Fly" in md
    assert "templates added" in md and "**1**" in md


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
            "15": 0.7, "16": 6.9, "23": 3.0,
            "7": {"20": 0.2},
            "26": {"1": 2, "3": 25},
        }},
        "V0002_POKEMON_IVYSAUR": {"2": {
            "1": 2, "4": 12, "5": 4, "8": {"1": 160, "2": 151, "3": 143},
            "9": {"__bytes__": quick}, "10": {"__bytes__": charge}, "23": 3.0,
        }},
        "WEATHER_AFFINITY_RAINY": {"25": {
            "1": 2, "2": {"__bytes__": base64.b64encode(_packed_varints([11, 13, 7])).decode()}}},
        "ITEM_POKE_BALL": {"3": {"1": 1, "2": 1}},
        "COMBAT_LEAGUE_GREAT": {"35": {"1": "great", "4": {"1": 1, "2": {"2": 1500}}}},
        "FRIENDSHIP_LEVEL_4": {"31": {"1": 90, "3": 1.1}},
        "V0006_POKEMON_CHARIZARD": {"2": {
            "1": 6, "4": 10, "5": 3,
            "8": {"1": 186, "2": 223, "3": 173},
            "9": {"__bytes__": quick}, "10": {"__bytes__": charge},
            # two Mega overrides (X = Fire/Dragon, Y = Fire/Flying)
            "51": [
                {"1": 2, "2": {"1": 186, "2": 273, "3": 213}, "5": 10, "6": 16},
                {"1": 3, "2": {"1": 186, "2": 319, "3": 212}, "5": 10, "6": 3},
            ],
        }},
        "V0214_MOVE_VINE_WHIP_FAST": {"4": {
            "1": 214, "3": 12, "4": 6.0, "12": 500, "15": 5, "11": "vine_whip_fast",
        }},
        "V0090_MOVE_SLUDGE_BOMB": {"4": {
            "1": 90, "3": 4, "4": 85.0, "12": 2500, "15": (1 << 64) - 50,
        }},
        "PLAYER_LEVEL_SETTINGS": {"12": {"3": {"__bytes__": cpm_b64}}},
        # Fire attack row: SE vs Grass(12)=1.6, resist vs Water(11)=0.625
        "POKEMON_TYPE_FIRE": {"8": {"2": 10, "1": {"__bytes__": _type_row({12: 1.6, 11: 0.625})}}},
        "POKEMON_TYPE_WATER": {"8": {"2": 11, "1": {"__bytes__": _type_row({10: 1.6})}}},
        "POKEMON_UPGRADE_SETTINGS": {"18": {
            "3": {"__bytes__": base64.b64encode(_packed_varints([1, 1, 2, 2])).decode()},
            "4": {"__bytes__": base64.b64encode(_packed_varints([200, 200, 400, 400])).decode()},
        }},
    }
    return Pokedex(by_id, source="unit")


def _type_row(overrides):
    import base64
    vals = [1.0] * 18
    for type_id, mult in overrides.items():
        vals[type_id - 1] = mult
    return base64.b64encode(struct.pack("<18f", *vals)).decode()


def test_sheet_core_fields():
    dex = _make_dex()
    s = dex.sheet("V0001_POKEMON_BULBASAUR")
    assert s["name"] == "Bulbasaur"
    assert s["dexNumber"] == 1
    assert s["types"] == ["Grass", "Poison"]
    assert s["baseStats"] == {"attack": 118, "defense": 111, "stamina": 128}
    assert s["baseCaptureRate"] == 0.2
    assert s["evolution"][0]["candyCost"] == 25


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


def test_mega_forms_are_exposed_with_overrides():
    dex = _make_dex()
    keys = dex.pokemon_keys()
    mega_keys = [k for k in keys if "::TEMPEVO::" in k]
    assert len(mega_keys) == 2  # Charizard X and Y

    x = dex.sheet("V0006_POKEMON_CHARIZARD::TEMPEVO::2")
    assert x["isMega"] is True
    assert x["name"] == "Mega X Charizard"
    assert x["types"] == ["Fire", "Dragon"]
    assert x["baseStats"] == {"attack": 273, "defense": 213, "stamina": 186}

    y = dex.sheet("V0006_POKEMON_CHARIZARD::TEMPEVO::3")
    assert y["types"] == ["Fire", "Flying"]
    assert y["baseStats"]["attack"] == 319
    # Mega inherits the base species movepool
    assert y["fastMoves"] == x["fastMoves"]


def test_move_dps_eps():
    dex = _make_dex()
    s = dex.sheet("V0001_POKEMON_BULBASAUR")
    sludge = s["chargeMoves"][0]            # power 85, energy -50, 2.5s
    assert sludge["dps"] == 34.0
    assert sludge["eps"] == -20.0


def test_type_matchups_and_chart():
    dex = _make_dex()
    # A Fire-type defender (Charizard f4=10) should be weak to Water
    charizard = dex.sheet("V0006_POKEMON_CHARIZARD")
    assert "Water" in charizard["weakTo"]
    chart = dex.type_chart_named()
    assert chart["Fire"]["Grass"] == 1.6
    assert chart["Fire"]["Water"] == 0.625


def test_power_up_summary():
    dex = _make_dex()
    s = dex.power_up_summary()
    assert s["totalCandy"] == 6           # 1+1+2+2
    assert s["totalStardust"] == 1200     # 200+200+400+400


def test_validate_runs_clean_on_synthetic_data():
    dex = _make_dex()
    r = dex.validate()
    assert r["pokemonChecked"] == 3
    assert r["unresolvedMoveIds"]["count"] == 0
    assert r["statOutliers"]["count"] == 0
    assert r["typeChartAttackers"] == 2


def test_weather_buddy_and_evolution_name():
    dex = _make_dex()
    # Rainy boosts Water/Electric/Bug in _make_dex
    assert "Water" in dex.weather_summary().get("Rainy", [])
    s = dex.sheet("V0001_POKEMON_BULBASAUR")
    assert s["buddyDistanceKm"] == 3.0
    assert s["evolution"][0]["evolvesTo"] == "Ivysaur"
    assert s["evolution"][0]["candyCost"] == 25


def test_items_leagues_friendship_templates():
    dex = _make_dex()
    items = dex.items()
    assert any(it["name"] == "Poke Ball" and it["itemId"] == 1 for it in items)
    leagues = {lg["name"]: lg["cpCap"] for lg in dex.leagues()}
    assert leagues.get("Great") == 1500
    fr = {f["level"]: f["attackBonusMultiplier"] for f in dex.friendship_levels()}
    assert fr.get(4) == 1.1
    assert "POKEMON_TYPE_FIRE" in dex.template_ids()
    assert dex.search_templates("type_fire") == ["POKEMON_TYPE_FIRE"]


def test_diff_detects_stat_change():
    from pogodecode.pokedex import diff_pokedex
    a = _make_dex()
    b = _make_dex()
    b._by_id["V0001_POKEMON_BULBASAUR"]["2"]["8"]["2"] = 200  # bump attack
    report = diff_pokedex(a, b)
    assert report["pokemonChanged"]["count"] == 1
    change = report["pokemonChanged"]["details"][0]
    assert change["changes"]["baseStats"]["new"]["attack"] == 200


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
    # (atk, def, sta, maxCP@L40, maxCP@L50) - L50 values match in-game.
    cases = {
        "V0001_POKEMON_BULBASAUR": (118, 111, 128, 1115, 1260),
        "V0006_POKEMON_CHARIZARD": (223, 173, 186, 2889, 3266),
        "V0150_POKEMON_MEWTWO": (300, 182, 214, 4178, 4724),
    }
    for tid, (atk, dfn, sta, cp40, cp50) in cases.items():
        s = dex.sheet(tid)
        assert s["baseStats"] == {"attack": atk, "defense": dfn, "stamina": sta}
        assert s["maxCpLevel40"] == cp40
        assert s["maxCpLevel50"] == cp50

    # The Level-50 multiplier must be integer-indexed (0.8403), not the 0.8653 cap.
    assert abs(dex.cp_multiplier_for_level(50) - 0.84030002) < 1e-6
    assert abs(dex.cp_multiplier_for_level(40) - 0.79030001) < 1e-6

    # Mega Charizard X/Y must be present with their override typing
    mega = {k for k in dex.pokemon_keys() if k.startswith("V0006_POKEMON_CHARIZARD::TEMPEVO::")}
    assert len(mega) == 2
    x = dex.sheet("V0006_POKEMON_CHARIZARD::TEMPEVO::2")
    assert x["types"] == ["Fire", "Dragon"]
    assert x["baseStats"] == {"attack": 273, "defense": 213, "stamina": 186}


@pytest.mark.skipif(_real() is None, reason="no real GAME_MASTER file available")
def test_real_file_movepools_and_elite_moves():
    from pogodecode.pokedex import load_pokedex
    dex = load_pokedex(_real())

    # Regression: Dragonite's packed fast-move list used to mis-decode as a
    # sub-message and vanish. It must contain its real fast moves.
    drag = {m["name"] for m in dex.sheet("V0149_POKEMON_DRAGONITE")["fastMoves"]}
    assert {"Dragon Breath", "Dragon Tail", "Steel Wing"} <= drag

    # Elite / legacy moves live in separate fields and must be surfaced.
    pol = dex.sheet("V0062_POKEMON_POLIWRATH")
    assert "Counter" in {m["name"] for m in pol["eliteFastMoves"]}
    mew = dex.sheet("V0150_POKEMON_MEWTWO")
    elite_charge = {m["name"] for m in mew["eliteChargeMoves"]}
    assert {"Psystrike", "Shadow Ball"} <= elite_charge
    # Mewtwo genuinely does not learn Counter in the data (neither pool).
    all_mew = {m["name"] for m in mew["fastMoves"] + mew["eliteFastMoves"]}
    assert "Counter" not in all_mew

    # With movepools decoded correctly, almost no Pokemon should look move-less
    # (Smeargle is the only legitimate case -- it copies moves via Sketch).
    v = dex.validate()
    assert v["pokemonWithoutFastMove"]["count"] <= 3
    assert v["unresolvedMoveIds"]["count"] == 0
    assert v["pokemonWithEliteChargeMove"] > 100


@pytest.mark.skipif(_real() is None, reason="no real GAME_MASTER file available")
def test_real_file_form_and_mega_required_moves():
    from pogodecode.pokedex import load_pokedex
    dex = load_pokedex(_real())

    def required(tid):
        return {m["name"] for m in dex.sheet(tid)["requiredMoves"]}

    # Mega-required move (field 77) on Rayquaza and its Mega temp-evo sheet.
    assert "Dragon Ascent" in required("V0384_POKEMON_RAYQUAZA")
    assert "Dragon Ascent" in required("V0384_POKEMON_RAYQUAZA::TEMPEVO::1")
    # Form-change signature moves (field 63).
    assert "Behemoth Blade" in required("V0888_POKEMON_ZACIAN_CROWNED_SWORD")
    assert "Behemoth Bash" in required("V0889_POKEMON_ZAMAZENTA_CROWNED_SHIELD")
    assert "Secret Sword" in required("V0647_POKEMON_KELDEO_RESOLUTE")
    # A normal Pokemon has no signature-move section (no false positives).
    assert dex.sheet("V0006_POKEMON_CHARIZARD")["requiredMoves"] == []

    # Unreleased OHKO moves are faithfully decoded but flagged, and reported.
    by_name = {m["name"]: m for m in dex.all_moves()}
    assert by_name["Horn Drill"]["placeholder"] is True
    assert by_name["Fissure"]["placeholder"] is True
    assert by_name["Fire Blast"]["placeholder"] is False
    ph = {n for n in dex.validate()["placeholderMoves"]["sample"]}
    assert {"Horn Drill", "Fissure"} <= ph


@pytest.mark.skipif(_real() is None, reason="no real GAME_MASTER file available")
def test_real_file_health_check_and_bundle():
    from pogodecode.pokedex import load_pokedex, export_bundle
    dex = load_pokedex(_real())

    # Drift-guard passes on a good file, and trips when the threshold is impossible.
    assert dex.health_check()["ok"] is True
    assert all(c["ok"] for c in dex.health_check()["checks"])
    assert dex.health_check(max_moveless=0)["ok"] is False   # 2 move-less (Smeargle)

    # Versioned bundle is self-describing and deterministic.
    b1 = export_bundle(dex, source_path=_real())
    b2 = export_bundle(dex, source_path=_real())
    assert b1["meta"]["version"] == b2["meta"]["version"]    # stable content key
    assert b1["meta"]["healthOk"] is True
    assert b1["meta"]["pokemonCount"] == len(dex.pokemon_keys())
    assert b1["sheets"] and "templateId" in b1["sheets"][0]
