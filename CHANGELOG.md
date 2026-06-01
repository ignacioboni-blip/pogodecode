# Changelog

All notable changes to this project are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-05-31

First public release.

### Decoder
- Schema-free protobuf wire-format decoder for the modern (binary) Pokémon GO
  `GAME_MASTER` file — no `.proto` schema needed, so it survives client updates.
- Tkinter GUI (`PoGoGameMasterDecoder`) and CLI to export clean JSON
  (`templatesById`, `templates`, `categories`), pretty or minified.
- **Packed-field correctness:** a packed repeated scalar (e.g. a Pokémon's
  move-id list) is byte-for-byte indistinguishable from a sub-message on the
  wire, so the schema-free decoder could silently mis-read it and drop the data.
  The decoder now accepts per-path hints; the GAME_MASTER layer applies them to
  Pokémon movepool fields (9/10/49/50), fixing ~200 Pokémon (e.g. Dragonite)
  whose fast moves previously decoded as a bogus nested message.

### Pokédex viewer (verification tool)
- Readable per-Pokémon sheets: typing, base stats, height/weight, base catch
  rate, fast/charge moves (power/energy/duration/DPS/EPS), evolution cost.
- **Max CP at Level 40, 50, and 51 (best buddy)** — using correct integer-level
  CP-multiplier indexing (`index = level - 1`); avoids the common ~6% L50 error.
- **Elite / legacy moves** (Elite TM, Community Day, event exclusives) shown
  separately — these live in distinct fields (49/50) and were previously hidden,
  e.g. Mewtwo's Psystrike / Shadow Ball, Poliwrath's Counter.
- **Form / Mega signature moves** surfaced — moves a Pokémon only gets through a
  Mega or form change, stored outside the normal pools (field 77 and the
  form-change struct 63): Rayquaza/Mega Rayquaza's Dragon Ascent, Crowned
  Zacian's Behemoth Blade, Crowned Zamazenta's Behemoth Bash, Keldeo's Secret
  Sword, etc.
- **Mega / Primal forms** (incl. Mega X / Y) with overridden stats and typing.
- **Type matchups**: per-Pokémon weaknesses/resistances + full 18×18 chart.
- **Weather boosts**, **buddy distance**, **power-up cost** tables.
- **Items**, **PvP leagues** (CP caps), **friendship** bonuses.
- **Validation** report: no-move Pokémon, unresolved move IDs, stat/type outliers.
- **Diff** two GAME_MASTER files to see exactly what changed between updates.
- Filter by type, sort by stat/CP, compare Pokémon side-by-side, and a generic
  search over every decoded template.

### Packaging
- One-click Windows build; CI builds standalone binaries for Windows, macOS and
  Linux and attaches them to GitHub Releases on version tags.
