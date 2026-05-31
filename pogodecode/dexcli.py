"""Command-line Pokédex: print an info sheet or export all sheets to JSON.

Usage::

    python -m pogodecode.dexcli GAME_MASTER --name BULBASAUR
    python -m pogodecode.dexcli GAME_MASTER --name MEWTWO
    python -m pogodecode.dexcli GAME_MASTER --export sheets.json
"""

from __future__ import annotations

import argparse
import json
import sys

from .pokedex import load_pokedex


def _format_sheet(s: dict) -> str:
    lines = [
        f"#{s['dexNumber']:04d}  {s['name']}    [{s['templateId']}]",
        f"  Type:     {' / '.join(s['types'] or ['—'])}",
        f"  Stats:    Atk {s['baseStats']['attack']}  "
        f"Def {s['baseStats']['defense']}  Sta {s['baseStats']['stamina']}",
    ]
    if s.get("maxCpLevel40") is not None:
        lines.append(f"  Max CP:   {s['maxCpLevel40']} (L40, perfect IV)")
    lines.append(f"  Size:     {s.get('heightM','?')} m / {s.get('weightKg','?')} kg")
    if s.get("baseCaptureRate") is not None:
        lines.append(f"  Capture:  {s['baseCaptureRate']*100:.1f}%")

    def moves(title, ms):
        lines.append(f"  {title}:")
        if not ms:
            lines.append("      —")
        for m in ms:
            extra = ""
            if "power" in m:
                extra = f"  power {m['power']:g}, energy {m['energy']}, {m['durationMs']/1000:g}s"
            lines.append(f"      {m['name']} ({m.get('type','?')}){extra}")

    moves("Fast moves", s["fastMoves"])
    moves("Charge moves", s["chargeMoves"])
    if s.get("evolution"):
        lines.append(f"  Evolve:   {s['evolution'].get('candyCost','?')} candy")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="pogodex", description="Pokémon GO GAME_MASTER info sheets.")
    p.add_argument("input", help="GAME_MASTER file or decoded JSON")
    p.add_argument("--name", help="filter by (sub)string, e.g. BULBASAUR or CHARIZARD")
    p.add_argument("--export", metavar="PATH", help="write all sheets to a JSON file")
    args = p.parse_args(argv)

    dex = load_pokedex(args.input)

    if args.export:
        with open(args.export, "w", encoding="utf-8") as fh:
            json.dump(dex.all_sheets(), fh, indent=2, ensure_ascii=False)
        print(f"wrote {len(dex.pokemon_keys())} sheets to {args.export}")
        return 0

    keys = dex.pokemon_keys()
    if args.name:
        needle = args.name.upper()
        keys = [k for k in keys if needle in k.upper()]
    if not keys:
        print("no matching Pokémon", file=sys.stderr)
        return 1
    for k in keys[:50]:
        print(_format_sheet(dex.sheet(k)))
        print()
    if len(keys) > 50:
        print(f"... {len(keys) - 50} more (narrow with --name)")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
