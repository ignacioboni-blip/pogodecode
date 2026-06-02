# Integration guide — use pogodecode in your own project

Everything you need to pull Pokémon GO mechanics into your app, bot, spreadsheet,
or data pipeline. Organized from "I just want a JSON file" to "I want the typed
Python API."

- [Install](#install)
- [Level 1 — just give me JSON](#level-1--just-give-me-json)
- [Level 2 — the decoder library](#level-2--the-decoder-library)
- [Level 3 — the Pokédex API](#level-3--the-pokédex-api)
- [The sheet schema](#the-sheet-schema)
- [The move schema](#the-move-schema)
- [Pokédex API reference](#pokédex-api-reference)
- [Recipes](#recipes)
- [Using it from other languages](#using-it-from-other-languages)
- [Versioning & stability](#versioning--stability)

---

## Install

No runtime dependencies — just Python **3.8+** and the standard library.

```bash
# from source (recommended while pre-PyPI)
git clone https://github.com/ignacioboni-blip/pogodecode
cd pogodecode
pip install -e .            # exposes `pogodecode` + console scripts
```

Or vendor it: the `pogodecode/` package is self-contained — copy it into your
project and `import pogodecode`. (Tkinter is only needed for the GUIs; the
decoder and Pokédex library never import it, so headless/server use is fine.)

After `pip install`, these console scripts exist: `pogodecode` (decoder) and
`pogodex` (Pokédex).

## Level 1 — just give me JSON

You don't have to write any code. Produce a JSON file and consume it from
anything (JavaScript, Go, Excel via Power Query, `jq`, …):

```bash
python -m pogodecode.cli GAME_MASTER -o game_master.json     # pretty
python -m pogodecode.cli GAME_MASTER -o game_master.min.json --minify
```

Or export ready-made, human-readable **Pokédex sheets** (names already resolved,
CP computed, moves named):

```bash
python -m pogodecode.dexcli GAME_MASTER --export sheets.json
```

See the [output format](../README.md#output-format) for the raw-decode shape and
[the sheet schema](#the-sheet-schema) for the exported sheets.

## Level 2 — the decoder library

The raw decode — exact, schema-free, keyed by protobuf field number:

```python
from pogodecode import decode_game_master, write_json

result = decode_game_master("GAME_MASTER")     # path or bytes
write_json(result, "game_master.json")          # pretty=False for minified

print(result["meta"]["templateCount"])          # 18707
charizard = result["templatesById"]["V0006_POKEMON_CHARIZARD"]
moves_settings = result["templatesById"]["COMBAT_SETTINGS"]
```

You can also decode an arbitrary protobuf blob directly:

```python
from pogodecode.protobuf_decoder import decode_message
msg = decode_message(raw_bytes)                       # {"1": ..., "2": {...}}
msg = decode_message(raw_bytes, packed_paths={(2, 9)})  # with a packed-field hint
```

## Level 3 — the Pokédex API

The friendly layer: names, stats, resolved moves, CP, type matchups, validation.
Accepts a **raw `GAME_MASTER`** or a **JSON file previously exported by this
tool**:

```python
from pogodecode.pokedex import load_pokedex

dex = load_pokedex("GAME_MASTER")
sheet = dex.sheet("V0006_POKEMON_CHARIZARD")

print(sheet["name"], sheet["types"])             # Charizard ['Fire', 'Flying']
print(sheet["maxCpLevel40"])                     # 2889
for m in sheet["chargeMoves"]:
    print(m["name"], m["type"], m["energy"])     # Fire Blast Fire -100
```

## The sheet schema

`dex.sheet(template_id)` returns a dict with this shape (a Mega/form override
returns the same keys; some keys are present only when relevant):

```jsonc
{
  "templateId": "V0006_POKEMON_CHARIZARD",
  "dexNumber": 6,
  "name": "Charizard",
  "form": null,                       // e.g. "CHARIZARD_NORMAL", "MUK_ALOLA"
  "isMega": false,                    // true for Mega/Primal override sheets
  "types": ["Fire", "Flying"],
  "weakTo": ["Rock", "Water", "Electric"],
  "resistantTo": ["Bug", "Grass", "Fighting", "Ground", "Steel", "Fire", "Fairy"],
  "baseStats": { "attack": 223, "defense": 173, "stamina": 186 },
  "heightM": 1.7,
  "weightKg": 90.5,
  "buddyDistanceKm": 3.0,
  "boostedWeather": ["Clear", "Windy"],
  "baseCaptureRate": 0.05,            // 0..1 (×100 for %)
  "fastMoves":   [ <move>, ... ],
  "chargeMoves": [ <move>, ... ],
  "eliteFastMoves":   [ <move>, ... ],   // legacy/Elite-TM (may be empty)
  "eliteChargeMoves": [ <move>, ... ],
  "requiredMoves":    [ <move>, ... ],   // form/Mega signature moves (may be empty)
  "maxCpLevel40": 2889,
  "maxCpLevel50": 3266,
  "maxCpLevel51BestBuddy": 3305,
  // evolution[] is present on Pokémon that evolve; fields are null when the
  // species is a final evolution. Example for a Charmander-stage Pokémon:
  "evolution": [ { "evolvesTo": "Charmeleon", "evolvesToId": 5, "candyCost": 25 } ],
  "secondChargeMove": { "stardust": 10000, "candy": 25 },   // when present
  "shadow": { "purificationStardust": 3000, "purificationCandy": 3 }  // when present
}
```

Notes:
- Elite moves carry `"elite": true`; required/signature moves carry
  `"required": true`.
- Mega / Primal forms appear as **their own sheets** keyed
  `…::TEMPEVO::<n>` (e.g. `V0006_POKEMON_CHARIZARD::TEMPEVO::2`). List all keys
  with `dex.pokemon_keys()`.

## The move schema

Every move (in `fastMoves`, `chargeMoves`, etc., and from `dex.all_moves()`):

```jsonc
{
  "id": 103,
  "name": "Fire Blast",
  "type": "Fire",
  "category": "Charge",      // "Fast" | "Charge"
  "power": 140,
  "energy": -100,            // fast moves gain energy (+), charge moves spend (−)
  "durationMs": 4000,
  "dps": 35.0,               // power / seconds  (PvE)
  "eps": -25.0,              // energy / seconds
  "pvpPower": 140,           // PvP stats when present (either may be null)
  "pvpEnergy": null
}
```

(An unresolved id appears as `{ "id": <n>, "name": "Move #<n>" }`.)

## Pokédex API reference

| Method | Returns |
|---|---|
| `sheet(template_id)` | full sheet dict (above) |
| `all_sheets()` | list of every Pokémon/form sheet |
| `pokemon_keys()` | every Pokémon/form key (incl. `…::TEMPEVO::n`) |
| `all_moves()` | list of every move dict |
| `move_name(move_id)` | resolved move name |
| `max_cp(atk, def, sta, level=40)` | integer Max CP |
| `cp_multiplier_for_level(level)` | CPM float (half-levels interpolated) |
| `cp_table(atk, def, sta, levels=...)` | CP at a set of levels |
| `power_up_summary()` | candy/stardust power-up costs |
| `type_matchups(type_ids)` | `{weakTo, resistantTo, multipliers}` |
| `type_chart_named()` | full 18×18 effectiveness chart by name |
| `weather_summary()` | `{weather: [boosted types]}` |
| `items()` | item list |
| `leagues()` | PvP leagues with CP caps |
| `friendship_levels()` | friendship bonuses |
| `validate()` | whole-file sanity report (see [BUGS.md](BUGS.md)) |
| `template_ids()` / `template(id)` / `search_templates(term)` | raw template access |

## Recipes

**Export a CSV of every Pokémon's stats and Max CP:**

```python
import csv
from pogodecode.pokedex import load_pokedex

dex = load_pokedex("GAME_MASTER")
with open("pokemon.csv", "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["dex", "name", "atk", "def", "sta", "cp40", "cp50", "types"])
    for s in dex.all_sheets():
        b = s["baseStats"]
        w.writerow([s["dexNumber"], s["name"], b["attack"], b["defense"],
                    b["stamina"], s["maxCpLevel40"], s["maxCpLevel50"],
                    "/".join(s["types"])])
```

**Find every Pokémon that can learn a given move (incl. elite/required):**

```python
def learners(dex, move_name):
    out = []
    for s in dex.all_sheets():
        pools = (s["fastMoves"] + s["chargeMoves"] + s["eliteFastMoves"]
                 + s["eliteChargeMoves"] + s["requiredMoves"])
        if any(m["name"] == move_name for m in pools):
            out.append(s["name"])
    return out

print(learners(dex, "Counter"))
```

**Diff two GAME_MASTER versions programmatically:**

```python
from pogodecode.pokedex import load_pokedex, diff_pokedex
report = diff_pokedex(load_pokedex("OLD"), load_pokedex("NEW"))
print(report["templatesAdded"], report["pokemonChanged"])
```

## Using it from other languages

The simplest cross-language path is to **run the decoder once** and consume the
JSON natively:

```bash
python -m pogodecode.dexcli GAME_MASTER --export sheets.json
```

```js
// Node
const sheets = require("./sheets.json");
const char = sheets.find(s => s.name === "Charizard");
```

The raw decode (`pogodecode.cli`) gives you field-numbered JSON if you want to
build your own mapping; the exported sheets give you names + CP already resolved.

## Versioning & stability

- **Template ids** (`V0006_POKEMON_CHARIZARD`, etc.) are stable across client
  updates — build your lookups on them.
- **Sheet keys** documented here are stable within a major version; new keys may
  be *added* in minor versions. We follow [SemVer](https://semver.org/); see
  [CHANGELOG.md](../CHANGELOG.md).
- **Raw field numbers** can change whenever Niantic updates the client — don't
  hard-code them in your app; let the Pokédex layer map them, or re-derive from
  template ids.
