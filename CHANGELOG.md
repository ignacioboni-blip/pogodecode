# Changelog

All notable changes to this project are documented here. This project adheres
to [Semantic Versioning](https://semver.org/).

## [1.0.1] - 2026-06-10

Bug-fix release.

### Fixed
- **macOS performance & font size.** The bundled Google Sans Flex is now a
  lightweight **static** Regular/Bold instance (~126 KB each) instead of a 4 MB
  variable font — macOS CoreText resolved the variable instance on every text
  draw, which made the app render noticeably slower. The theme now also keeps
  each platform's **native point size** (it no longer forces 10 pt), so the UI
  no longer looks small on macOS. Fonts are registered once per process.
  ([BUGS B7](docs/BUGS.md#b7))
- **Viewer crash on the wrong JSON.** Opening a Pokédex *sheets* export
  (`--export`, a JSON list) or a *bundle* (`--bundle`) in the viewer crashed with
  `AttributeError: 'list' object has no attribute 'get'`. `load_pokedex` now
  detects these and shows a clear message pointing at the raw `GAME_MASTER` or the
  decoder's `game_master.json`. ([BUGS B6](docs/BUGS.md#b6))

### Verified
- Decodes the latest `GAME_MASTER` cleanly (drift-guard green): **no CP-formula
  change**; the update is event-pass rotation plus one new move (Glaive Rush) and
  additive movepool updates for 47 Pokémon. See
  [docs/updates/](docs/updates/CHANGELOG-ee75db6f.md).

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
- **Validation** report: no-move Pokémon, unresolved move IDs, stat/type outliers,
  and **unreleased placeholder moves** (Horn Drill 9000 / Fissure 9001 — Niantic's
  sentinel power for OHKO moves assigned to no Pokémon; decoded faithfully but
  flagged `placeholder` and marked `(unreleased)` so they don't pollute output).
- **Diff** two GAME_MASTER files to see exactly what changed between updates.
- Filter by type, sort by stat/CP, compare Pokémon side-by-side, and a generic
  search over every decoded template.

### Keeping data current (pipeline)
- **Drift-guard** (`dexcli --check`, `Pokedex.health_check()`): balance-independent
  structural assertions that **exit non-zero** when the data looks wrong (move ids
  not resolving, Pokémon going move-less, stat/type outliers, bad CP multiplier or
  type chart) — i.e. exactly how a renumbered mapped field manifests. Use it as a
  CI gate so a broken GAME_MASTER never ships.
- **Versioned export** (`dexcli --bundle`, `export_bundle()`): a self-describing
  JSON with stamped `meta` (tool version, source, a sha256 `version` to cache-bust
  on, timestamp, counts) + health report + every sheet.
- **Markdown changelog** (`dexcli --diff … --format md`, `diff_to_markdown()`):
  human-readable "what changed" between two GAME_MASTER versions.
- **Scheduled GitHub Action** (`data-refresh.yml`): fetch → drift-guard → versioned
  bundle + changelog → publish a rolling `data-latest` release; publishes nothing
  if the guard fails. Point it at your source via the `GAME_MASTER_URL` variable.

### Look & feel
- **Embedded fonts** — the GUI ships with **Google Sans Flex** (default UI font,
  bundled as lightweight static Regular/Bold instances ~126 KB each) and
  **Quicksand** (display), both SIL OFL; registered once per process on
  Windows/macOS/Linux with graceful fallback. The theme keeps each platform's
  native point size, so the UI doesn't shrink on macOS (and the static font
  renders much faster there than the original 4 MB variable font).
- **Font picker** — **View → Choose font…** lets you use any font installed on
  your machine (searchable, with live preview); remembered across sessions.
- **Self-contained light & dark theme** — a pure-ttk theme (styled widgets only,
  no OS window hacks) that renders identically on Windows/macOS/Linux; toggle via
  **View → Dark mode** (remembered across sessions). Replaces the earlier
  `pywinstyles`/acrylic approach, which washed out light mode on Windows and
  couldn't be themed reliably across platforms.
- All theming is best-effort and isolated to the GUIs — the CLI/library remain
  dependency-free and headless-safe.

### Legal
- Comprehensive **legal notices** ([docs/LEGAL.md](docs/LEGAL.md), [NOTICE](NOTICE),
  expanded README section): unofficial/fan-project disclaimer, nominative
  trademark use, ships-no-game-data statement, acceptable-use & ToS
  responsibility, no-warranty, third-party (OFL fonts) attribution, and a
  rights-holder takedown contact path.

### Packaging
- One-click Windows build; CI builds standalone binaries for Windows, macOS and
  Linux and attaches them to GitHub Releases on version tags.
