# PoGo GAME_MASTER Decoder

A Windows desktop tool that decodes the **Pokémon GO `GAME_MASTER` file** into
clean, usable **JSON**.

The classic decoders (e.g. the old
[`pogo-game-master-decoder`](https://github.com/apavlinovic/pogo-game-master-decoder)
and the JSON-era Silph Road / PoGoHub guides) target the *legacy* GAME_MASTER
format. Modern GAME_MASTER files are a **binary protobuf**, so those tools just
produce garbage or crash. This project fixes that.

## Why it doesn't go out of date

Niantic does **not** publish the `.proto` schema for GAME_MASTER, and they
reshuffle fields with almost every client update — which is exactly why
schema-bound decoders rot.

This decoder reads the **protobuf wire format directly** (pure standard
library, no schema). It cannot break when Niantic adds or moves a setting:

- **Template IDs are exact** — they are plain strings stored in the file
  (e.g. `V0003_POKEMON_VENUSAUR`, `COMBAT_SETTINGS`, `EXTENDED_V0001_POKEMON_BULBASAUR`).
- **Settings payloads** are decoded into nested objects keyed by their numeric
  protobuf **field number** (Niantic ships no field names), with values typed
  as ints, floats, strings, nested messages, or base64 for raw binary.

## Output format

```jsonc
{
  "meta": {
    "source": "GAME_MASTER",
    "sizeBytes": 2924749,
    "templateCount": 18707,
    "categoryCount": 1598,
    "skippedEntries": 0,
    "decodedAt": "2026-05-31T07:30:18Z"
  },
  "templatesById": {
    "EXTENDED_V0001_POKEMON_BULBASAUR": {
      "162": {
        "66": { "1": 0.343, "2": 0.35, "3": 0.525 },   // sizes
        "67": { "9": { "1": 19.04, "2": 25.0, "3": 14.0 } }  // stats
      }
    }
  },
  "templates":  [ { "templateId": "...", "data": { ... } } ],  // file order
  "categories": { "POKEMON": ["V0001_POKEMON_BULBASAUR", ...], "MOVE": [...] }
}
```

- `templatesById` — fast lookup by template id (the JSON "API" surface).
- `templates` — every entry in original file order (safe if an id repeats).
- `categories` — template ids grouped by their prefix.
- Binary blobs that aren't text or sub-messages appear as
  `{ "__bytes__": "<base64>" }`.

## Using the Windows app

1. Build or download `PoGoGameMasterDecoder.exe` (see **Building** below).
2. Run it. Click **Browse…** and pick your `GAME_MASTER` file.
3. Choose where to save the JSON (defaults next to the input file).
4. Click **Decode → JSON**. A ~3 MB GAME_MASTER decodes in a few seconds into
   roughly 20 MB of pretty-printed JSON (tick **Minify** for a smaller file).

## Building the .exe (on Windows)

```bat
build_windows.bat
```

This creates a virtual environment, installs PyInstaller, and produces
`dist\PoGoGameMasterDecoder.exe` — a single self-contained file that needs no
Python install on the target machine. (Equivalent manual step:
`pyinstaller pogodecode.spec`.)

## Command-line use (any OS)

No dependencies — just Python 3.8+:

```bash
python -m pogodecode.cli GAME_MASTER -o game_master.json --stats
python -m pogodecode.cli GAME_MASTER --minify          # compact output
```

## As a Python library

```python
from pogodecode import decode_game_master, write_json

result = decode_game_master("GAME_MASTER")
write_json(result, "game_master.json")

venusaur = result["templatesById"]["V0003_POKEMON_VENUSAUR"]
```

## Where to get a GAME_MASTER file

The file ships inside the Pokémon GO app's downloaded assets. Community guides
explain how to pull it from the device cache:

- https://www.reddit.com/r/TheSilphRoad/comments/5r9kvd/guide_how_to_extract_decode_the_game_master_file/
- https://pokemongohub.net/post/guide/guide-decode-pokemon-go-game_master-file/

## Running the tests

```bash
pip install pytest
pytest                                   # unit tests (no fixtures needed)
POGO_GAME_MASTER=/path/to/GAME_MASTER pytest   # also runs the integration test
```

## Project layout

```
pogodecode/
  protobuf_decoder.py   schema-free protobuf wire-format decoder
  gamemaster.py         GAME_MASTER structure -> JSON-ready dict
  cli.py                command-line entry point
  gui.py                Tkinter desktop UI
run_gui.py              .exe entry point
pogodecode.spec         PyInstaller build spec
build_windows.bat       one-click Windows build
tests/test_decoder.py   unit + integration tests
```

## Legal

`GAME_MASTER` content is © Niantic / The Pokémon Company. This tool only
decodes a file you already have; it ships no game data.
