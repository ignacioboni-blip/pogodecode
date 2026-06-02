<h1 align="center">PoGo GAME_MASTER Tools</h1>

<p align="center">
  <img src="assets/icon.png" width="96" alt="logo"><br>
  <b>Decode the Pokémon GO <code>GAME_MASTER</code> file to clean JSON — and verify it in a Pokédex viewer.</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT">
  <img src="https://img.shields.io/badge/python-3.8%2B-blue" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/platforms-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey" alt="platforms">
  <img src="https://img.shields.io/badge/runtime%20deps-none-brightgreen" alt="no deps">
</p>

| Pokédex Viewer | GAME_MASTER Decoder |
|:---:|:---:|
| ![Pokédex Viewer](docs/screenshots/viewer.png) | ![GAME_MASTER Decoder](docs/screenshots/decoder.png) |

<sub>Real screenshots of the apps decoding a current GAME_MASTER (18,707 templates / 2,577 Pokémon forms). The UI ships with the bundled <b>Google Sans Flex</b> font and a light/dark theme (see <a href="#theming--fonts">Theming &amp; fonts</a>).</sub>

---

## Table of contents

- [What is this?](#what-is-this)
- [Pick your path (quickstart)](#pick-your-path-quickstart)
- [Tool 1 — the GAME_MASTER Decoder](#tool-1--the-game_master-decoder)
- [Tool 2 — the Pokédex Viewer](#tool-2--the-pokédex-viewer)
- [How it works (methodology)](#how-it-works-methodology)
- [What it can and can't do](#what-it-can-and-cant-do)
- [Bugs found & fixed](#bugs-found--fixed)
- [Use it in your own project](#use-it-in-your-own-project)
- [Build from source](#build-from-source)
- [Where to get a GAME_MASTER file](#where-to-get-a-game_master-file)
- [Tests, layout, contributing](#tests-layout-contributing)
- [License & legal](#license--legal)

---

## What is this?

Two small, dependency-free apps that share one engine:

| App | What it does |
|---|---|
| **GAME_MASTER Decoder** | Turns the binary `GAME_MASTER` into clean, schema-free **JSON** |
| **Pokédex Viewer** | Reads that data into readable, verifiable **info sheets** — stats, moves, types, CP, weather, items, leagues, diffs |

**The problem it solves.** `GAME_MASTER` defines Pokémon GO's mechanics (stats,
moves, CP formulas, costs…). Niantic ships it as a **binary protobuf** and does
**not** publish the schema, reshuffling field numbers almost every update. The
classic decoders (the old
[`pogo-game-master-decoder`](https://github.com/apavlinovic/pogo-game-master-decoder),
the JSON-era Silph Road / PoGoHub guides) target the *legacy* format and now just
produce garbage or crash. This project reads the **protobuf wire format directly**,
so it keeps working across client updates. [Read how →](docs/METHODOLOGY.md)

## Pick your path (quickstart)

Three ways in, depending on what you want. **No setup needed for the first one.**

<details open>
<summary><b>🟢 "I just want the apps"</b> — no Python, no command line</summary>

<br>

Download a prebuilt, standalone app from the
[**Releases**](https://github.com/ignacioboni-blip/pogodecode/releases) page
(Windows / macOS / Linux):

- `PoGoGameMasterDecoder` — decode → JSON
- `PoGoPokedexViewer` — browse & verify

Run it, click **Browse…**, pick your `GAME_MASTER`, go.

> First-run warning? The binaries aren't code-signed (signing needs a paid cert),
> so Windows SmartScreen / macOS Gatekeeper may prompt. Choose *More info → Run
> anyway*, or [build from source](#build-from-source).

</details>

<details>
<summary><b>🟡 "I want a JSON / data file"</b> — one command, any OS</summary>

<br>

Needs Python 3.8+ (standard library only):

```bash
# raw, exact decode → JSON (field-numbered)
python -m pogodecode.cli GAME_MASTER -o game_master.json

# human-readable Pokédex sheets → JSON (names + CP already resolved)
python -m pogodecode.dexcli GAME_MASTER --export sheets.json

# read one Pokémon right in the terminal
python -m pogodecode.dexcli GAME_MASTER --name CHARIZARD
```

</details>

<details>
<summary><b>🔵 "I'm a developer"</b> — import it as a library</summary>

<br>

```python
from pogodecode.pokedex import load_pokedex

dex = load_pokedex("GAME_MASTER")            # raw file OR an exported .json
s = dex.sheet("V0006_POKEMON_CHARIZARD")
print(s["name"], s["types"], s["maxCpLevel40"])   # Charizard ['Fire','Flying'] 2889
```

Full API, sheet schema, and recipes → **[INTEGRATION.md](docs/INTEGRATION.md)**

</details>

## Tool 1 — the GAME_MASTER Decoder

Converts the binary file into JSON. Use the GUI (`PoGoGameMasterDecoder`) or the
CLI:

```bash
python -m pogodecode.cli GAME_MASTER -o game_master.json   # pretty (default)
python -m pogodecode.cli GAME_MASTER --minify              # compact
python -m pogodecode.cli GAME_MASTER --stats               # timing/size to stderr
```

A ~3 MB GAME_MASTER decodes in a few seconds into ~19 MB of JSON.

<details>
<summary><b>Output format</b> (click to expand)</summary>

```jsonc
{
  "meta": {
    "source": "GAME_MASTER", "sizeBytes": 2924749,
    "templateCount": 18707, "categoryCount": 1598,
    "skippedEntries": 0, "decodedAt": "2026-05-31T07:30:18Z"
  },
  "templatesById": {                       // fast lookup by template id
    "V0006_POKEMON_CHARIZARD": { "2": { "8": { "1": 186, "2": 223, "3": 173 }, ... } }
  },
  "templates":  [ { "templateId": "...", "data": { ... } } ],   // original file order
  "categories": { "POKEMON": ["V0001_POKEMON_BULBASAUR", ...], "MOVE": [...] }
}
```

- `templatesById` — fast lookup by **template id** (the stable, exact key).
- `templates` — every entry in file order (safe even if an id repeats).
- `categories` — template ids grouped by their prefix.
- Settings payloads are keyed by **numeric protobuf field number** (Niantic ships
  no field names). Binary blobs that aren't text or sub-messages appear as
  `{ "__bytes__": "<base64>" }`.

</details>

## Tool 2 — the Pokédex Viewer

Reads a GAME_MASTER (or a decoder-exported JSON) and shows a readable sheet per
Pokémon — names and values, no field numbers — designed for **verifying** the
decode. Highlights:

- Dex number, name, form, **typing**, height/weight, **base catch rate**
- **Base stats** and **Max CP at L40 / L50 / L51 (best buddy)** — correct
  integer-level CPM indexing (avoids the common ~6% L50 error)
- **Fast & charge moves** with type, power, energy, duration, and **DPS/EPS**
- **Elite / legacy moves** (Elite TM / Community Day) — e.g. Mewtwo's Shadow Ball
- **Form / Mega signature moves** — Mega Rayquaza's Dragon Ascent, Crowned
  Zacian's Behemoth Blade, Keldeo's Secret Sword…
- **Mega / Primal forms** (incl. Mega X / Y) and **regional forms** as entries
- **Type matchups** per Pokémon + a full **18×18 type chart**
- **Weather boosts**, **buddy distance**, **power-up & CP tables**
- **Items**, **PvP leagues** (CP caps), **friendship** bonuses
- **Validation** report, **filter/sort/compare**, **template search**, and a
  **Diff** tab to see exactly what changed between two GAME_MASTER versions

```bash
python -m pogodecode.dexcli GAME_MASTER --name CHARIZARD    # print a sheet
python -m pogodecode.dexcli GAME_MASTER --moves            # every move + stats
python -m pogodecode.dexcli GAME_MASTER --type-chart       # 18×18 effectiveness
python -m pogodecode.dexcli GAME_MASTER --validate         # whole-file sanity sweep
python -m pogodecode.dexcli GAME_MASTER --weather          # weather → boosted types
python -m pogodecode.dexcli GAME_MASTER --items            # items
python -m pogodecode.dexcli GAME_MASTER --leagues          # PvP CP caps
python -m pogodecode.dexcli GAME_MASTER --template COMBAT_SETTINGS
python -m pogodecode.dexcli GAME_MASTER --search FRIENDSHIP
python -m pogodecode.dexcli OLD_GAME_MASTER --diff NEW_GAME_MASTER --format md  # changelog
python -m pogodecode.dexcli GAME_MASTER --export sheets.json
python -m pogodecode.dexcli GAME_MASTER --check        # drift-guard (CI gate; exit≠0 on bad data)
python -m pogodecode.dexcli GAME_MASTER --bundle data.json   # versioned, stamped export
```

## Theming & fonts

Both apps ship with a clean, modern look out of the box:

- **Bundled font.** The UI uses **Google Sans Flex** as its default font, with
  **Quicksand** for display text — both [SIL OFL](pogodecode/assets/fonts/)
  licensed and **embedded in the app**, so they render the same on every machine
  with nothing to install. Fonts are registered at runtime (Windows / macOS /
  Linux); if registration isn't possible, the app falls back to the system font.
- **Light & dark themes.** Toggle via **View → Dark mode** (remembered between
  sessions).
- **Native Windows styling.** On Windows, the title bar is styled to match via the
  optional [`pywinstyles`](https://pypi.org/project/pywinstyles/) package
  (`pip install pywinstyles`); it's bundled in the prebuilt `.exe`. Everything is
  best-effort — a missing dependency or unsupported platform silently falls back
  to the default look and never breaks the app.

## How it works (methodology)

The one-paragraph version: a protobuf message is a flat list of
`(field-number, wire-type, payload)` fields. We decode **by wire type, with no
schema**, keyed by field number — so adding/moving a field never breaks the
decode. The genuinely stable information, the **template ids**
(`V0006_POKEMON_CHARIZARD`), are plain strings in the file, so consumers can
always find their data by id. A small, documented **field map** then names the
handful of fields the Pokédex needs.

The one subtlety worth knowing: a "packed" array of numbers (like a move list) is
byte-for-byte identical to a sub-message on the wire, so a pure guess sometimes
mis-decodes it. We resolve this with **path-scoped hints** applied *only* to
Pokémon move fields — keeping the schema-free guarantee everywhere else.

📖 **Full write-up:** [docs/METHODOLOGY.md](docs/METHODOLOGY.md) — wire format
primer, schema-free decoding, the packed-field ambiguity, the field map, and the
CP math.

## What it can and can't do

**It can** give you every game *mechanic*: base stats, typing, all moves (incl.
elite & signature), type effectiveness, CP & power-up tables, catch rates,
buddy/evolution costs, weather boosts, items, leagues, friendship.

**It cannot** give you spawns, raid bosses, egg pools, or research rewards —
**that data is simply not in `GAME_MASTER`.** It's event-driven, server-side
data Niantic rotates weekly. No decoder can extract it from this file. (The only
spawn-adjacent value present is gender ratio.)

> **Where Megas live:** Megas/Primals aren't separate templates — they're
> *temporary-evolution overrides* (field 51) inside the base species, listed
> separately by the viewer (e.g. "Mega Y Charizard").

Full limitations & caveats → [docs/BUGS.md](docs/BUGS.md#known-limitations-by-design)

## Bugs found & fixed

This tool is only trustworthy if it's honest about where it was wrong. Summary
(full detail and "potential bugs to watch" in **[docs/BUGS.md](docs/BUGS.md)**):

| # | Bug | Status |
|---|-----|--------|
| B1 | ~200 Pokémon (e.g. **Dragonite**) silently lost their fast moves — packed move bytes mis-decoded as a sub-message | ✅ Fixed (path-scoped decode hints; false "no fast move" 203 → 2) |
| B2 | **Level-50 CP** off by ~6% — wrong CP-multiplier index | ✅ Fixed (integer-level indexing, `index = level − 1`) |
| B3 | **Elite / legacy moves** (e.g. Mewtwo Shadow Ball, Poliwrath Counter) not shown | ✅ Fixed (fields 49/50 surfaced) |
| B4 | **Form / Mega signature moves** (Dragon Ascent, Behemoth Blade/Bash, Secret Sword) not shown | ✅ Fixed (fields 77 & 63 surfaced) |
| B5 | **Horn Drill / Fissure** showed power 9000/9001 — Niantic's sentinel for unreleased OHKO moves (faithful data, not a decode bug) | ✅ Handled (flagged `placeholder`, marked `(unreleased)`, counted in `validate()`) |

## Use it in your own project

Zero runtime dependencies; vendor the `pogodecode/` folder or `pip install -e .`.

```python
from pogodecode import decode_game_master, write_json   # raw decode
from pogodecode.pokedex import load_pokedex             # friendly sheets

write_json(decode_game_master("GAME_MASTER"), "game_master.json")

dex = load_pokedex("GAME_MASTER")
for s in dex.all_sheets():
    print(s["dexNumber"], s["name"], s["maxCpLevel40"])
```

The complete **API reference**, **sheet & move schema**, copy-paste **recipes**
(CSV export, "who learns move X", programmatic diff), and **other-language**
usage are in → **[docs/INTEGRATION.md](docs/INTEGRATION.md)**.

## Keep a companion site up to date (pipeline)

The decode never crashes on Niantic's updates, but "never crashes" isn't "never
silently wrong" — if a *mapped* field is renumbered, values can drift without an
error. So the recommended operating model gates every refresh behind a check:

```
fetch new GAME_MASTER → --check (drift-guard) → on PASS: --bundle versioned JSON
                                              → --diff --format md (changelog)
                                              → publish for your site to pull
```

- **`--check`** runs balance-independent structural assertions (all move ids
  resolve, ~no move-less Pokémon, no stat/type outliers, CP multiplier sane, type
  chart complete) and **exits non-zero** if any trip — so a broken/renumbered
  GAME_MASTER never reaches your site.
- **`--bundle`** writes a self-describing JSON: stamped `meta` (tool version,
  source, a **sha256 `version`** to cache-bust on, timestamp, counts), the health
  report, and every sheet.
- **`--diff … --format md`** emits a human changelog (added/removed templates,
  per-Pokémon stat/type/move changes) so you can show "what changed."

A ready-to-use **scheduled GitHub Action** (`.github/workflows/data-refresh.yml`)
wires this together: point it at your GAME_MASTER source (a repo variable
`GAME_MASTER_URL` or a manual run input), and it fetches → guards → publishes the
versioned JSON + changelog as a rolling `data-latest` release for your site to
consume. It **publishes nothing if the drift-guard fails.**

> **Reality check.** This powers the *static mechanics* (stats, moves, types, CP,
> costs, items, leagues) reliably. It **cannot** provide spawns, raids, eggs, or
> research — that data isn't in GAME_MASTER. See
> [docs/BUGS.md](docs/BUGS.md#known-limitations-by-design).

## Build from source

**Windows (one click):**

```bat
build_windows.bat
```

Creates a venv, installs PyInstaller, and produces two self-contained apps in
`dist\` that need no Python on the target machine. Cross-platform equivalent:

```bash
pip install pyinstaller
pyinstaller pogodecode.spec        # builds both apps for the current OS
```

CI builds all three platforms and attaches them to a GitHub Release on every
`v*` tag (`.github/workflows/`).

## Where to get a GAME_MASTER file

It ships inside the Pokémon GO app's downloaded assets. This project ships **no**
game data — you supply your own file. Community guides on pulling it from the
device cache:

- https://www.reddit.com/r/TheSilphRoad/comments/5r9kvd/guide_how_to_extract_decode_the_game_master_file/
- https://pokemongohub.net/post/guide/guide-decode-pokemon-go-game_master-file/

## Tests, layout, contributing

```bash
pip install pytest pyflakes
pytest                                          # unit tests (no fixtures needed)
POGO_GAME_MASTER=/path/to/GAME_MASTER pytest    # + real-file integration tests
pyflakes pogodecode                             # lint
```

```
pogodecode/
  protobuf_decoder.py   schema-free protobuf wire-format decoder
  gamemaster.py         GAME_MASTER structure → JSON-ready dict (+ decode hints)
  pokedex.py            field map: decoded data → named Pokémon/move sheets
  cli.py / dexcli.py    command-line entry points (decoder / Pokédex)
  gui.py / viewer.py    Tkinter UIs (decoder / Pokédex viewer)
  _icon.py / _config.py embedded icon + remembered-folder helper
docs/                   METHODOLOGY · INTEGRATION · BUGS · LEGAL · screenshots
pogodecode/assets/fonts/ embedded UI fonts (Google Sans Flex, Quicksand; SIL OFL)
tests/                  unit + integration tests
pogodecode.spec         PyInstaller build spec (both apps)
.github/workflows/      CI: lint, test, build Win/macOS/Linux, release on tags
```

Before sending a change: run `pytest` and `pyflakes pogodecode`. Version history
is in [CHANGELOG.md](CHANGELOG.md); releases follow [SemVer](https://semver.org/).

## License & legal

**Code:** [MIT](LICENSE). **Bundled fonts:** SIL OFL 1.1 (see
[NOTICE](NOTICE) and [`pogodecode/assets/fonts/`](pogodecode/assets/fonts/)).

> **Unofficial fan project — please read.** pogodecode is **not** created,
> sponsored, endorsed by, or affiliated with **Niantic**, **Nintendo**, **The
> Pokémon Company**, **Game Freak**, or **Creatures Inc.** *Pokémon*, *Pokémon
> GO*, and all related names and logos are trademarks of their respective owners,
> used here **nominatively only** to describe what the tool interoperates with.
>
> This project ships **no game data, assets, or `GAME_MASTER` file** — it is a
> format **decoder** that runs on a file **you already possess**. It does **not**
> connect to Niantic's servers. It exists for **interoperability, analysis, and
> education**.
>
> **You are responsible** for obtaining any `GAME_MASTER` lawfully and for
> complying with **Niantic's Terms of Service** and applicable law in your
> jurisdiction. The software is provided **"as is", without warranty**, and the
> decoded output may be incomplete or incorrect — don't rely on it for anything
> critical.
>
> **Rights holders:** if you believe anything here oversteps fair/nominative use,
> open an issue titled `LEGAL / takedown request` or contact the maintainer — it
> will be **reviewed and addressed promptly**.

📜 **Full text:** [docs/LEGAL.md](docs/LEGAL.md) · [NOTICE](NOTICE)

*This is not legal advice.*
