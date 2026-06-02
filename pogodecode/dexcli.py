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

from . import __version__
from .pokedex import load_pokedex


def _format_sheet(s: dict) -> str:
    lines = [
        f"#{s['dexNumber']:04d}  {s['name']}    [{s['templateId']}]",
        f"  Type:     {' / '.join(s['types'] or ['—'])}",
        f"  Stats:    Atk {s['baseStats']['attack']}  "
        f"Def {s['baseStats']['defense']}  Sta {s['baseStats']['stamina']}",
    ]
    if s.get("maxCpLevel40") is not None:
        lines.append(f"  Max CP:   L40 {s['maxCpLevel40']}  /  L50 {s.get('maxCpLevel50','?')}"
                     f"  /  L51 best-buddy {s.get('maxCpLevel51BestBuddy','?')}  (perfect IV)")
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
    if s.get("eliteFastMoves"):
        moves("Elite/legacy fast moves", s["eliteFastMoves"])
    if s.get("eliteChargeMoves"):
        moves("Elite/legacy charge moves", s["eliteChargeMoves"])
    if s.get("requiredMoves"):
        moves("Required/signature moves (form/Mega)", s["requiredMoves"])
    for e in s.get("evolution", []) or []:
        target = e.get("evolvesTo") or e.get("evolvesToId")
        lines.append(f"  Evolve:   → {target} ({e.get('candyCost','?')} candy)")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="pogodex", description="Pokémon GO GAME_MASTER info sheets.")
    p.add_argument("--version", action="version", version=f"pogodex {__version__}")
    p.add_argument("input", help="GAME_MASTER file or decoded JSON")
    p.add_argument("--name", help="filter by (sub)string, e.g. BULBASAUR or CHARIZARD")
    p.add_argument("--export", metavar="PATH", help="write all sheets to a JSON file")
    p.add_argument("--moves", action="store_true", help="list every move with stats")
    p.add_argument("--type-chart", action="store_true", help="print the type-effectiveness chart")
    p.add_argument("--validate", action="store_true", help="print a data sanity-check report")
    p.add_argument("--weather", action="store_true", help="print weather -> boosted types")
    p.add_argument("--items", action="store_true", help="list all items")
    p.add_argument("--leagues", action="store_true", help="list PvP leagues with CP caps")
    p.add_argument("--template", metavar="ID", help="print one decoded template by id")
    p.add_argument("--search", metavar="TERM", help="list template ids matching TERM")
    p.add_argument("--diff", metavar="OTHER", help="diff this file against another GAME_MASTER/JSON")
    p.add_argument("--format", choices=("json", "md"), default="json",
                   help="output format for --diff (json or markdown changelog)")
    p.add_argument("--check", action="store_true",
                   help="run the drift-guard; exit non-zero if the data looks broken")
    p.add_argument("--max-moveless", type=int, default=5,
                   help="--check: max Pokémon allowed with no fast/charge move (default 5)")
    p.add_argument("--bundle", metavar="PATH",
                   help="write a versioned bundle (stamped meta + health + sheets) to PATH")
    args = p.parse_args(argv)

    if args.diff:
        from .pokedex import diff_files, diff_to_markdown
        report = diff_files(args.input, args.diff)
        if args.format == "md":
            print(diff_to_markdown(report))
        else:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    dex = load_pokedex(args.input)

    if args.check:
        report = dex.health_check(max_moveless=args.max_moveless)
        for c in report["checks"]:
            print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']:<24} {c['detail']}")
        ok = report["ok"]
        print(f"\n{'OK — data looks healthy' if ok else 'FAILED — see above'}",
              file=sys.stderr)
        return 0 if ok else 1

    if args.bundle:
        from .pokedex import export_bundle
        bundle = export_bundle(dex, source_path=args.input)
        with open(args.bundle, "w", encoding="utf-8") as fh:
            json.dump(bundle, fh, ensure_ascii=False, separators=(",", ":"))
        m = bundle["meta"]
        print(f"wrote {m['pokemonCount']} sheets to {args.bundle}  "
              f"(version {m['version'][:12]}, health {'ok' if m['healthOk'] else 'FAILED'})")
        return 0 if bundle["meta"]["healthOk"] else 1

    if args.weather:
        print(json.dumps(dex.weather_summary(), indent=2, ensure_ascii=False)); return 0
    if args.items:
        print(json.dumps(dex.items(), indent=2, ensure_ascii=False)); return 0
    if args.leagues:
        print(json.dumps(dex.leagues(), indent=2, ensure_ascii=False)); return 0
    if args.search:
        for tid in dex.search_templates(args.search):
            print(tid)
        return 0
    if args.template:
        print(json.dumps(dex.template(args.template), indent=2, ensure_ascii=False)); return 0
    if args.validate:
        print(json.dumps(dex.validate(), indent=2, ensure_ascii=False))
        return 0
    if args.type_chart:
        print(json.dumps(dex.type_chart_named(), indent=2, ensure_ascii=False))
        return 0
    if args.moves:
        for m in dex.all_moves():
            tag = "  (unreleased placeholder)" if m.get("placeholder") else ""
            print(f"{m['name']:<28} {m['type']:<9} {m['category']:<6} "
                  f"pow {m['power']:<5g} eng {m['energy']:<5} "
                  f"{m['durationMs']/1000:>4g}s  DPS {m['dps']:<6} EPS {m['eps']}{tag}")
        return 0

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
