# Methodology — how the decoder works

This document explains, from the ground up, how `pogodecode` turns the binary
`GAME_MASTER` file into clean data. You do **not** need to read this to use the
tools — it's here for the curious, for contributors, and for anyone adapting
the approach to another protobuf-without-a-schema problem.

- [1. The problem](#1-the-problem)
- [2. A 5-minute primer on protobuf wire format](#2-a-5-minute-primer-on-protobuf-wire-format)
- [3. Schema-free decoding](#3-schema-free-decoding)
- [4. The GAME_MASTER layer](#4-the-game_master-layer)
- [5. The fundamental ambiguity (and how we resolve it)](#5-the-fundamental-ambiguity-and-how-we-resolve-it)
- [6. The Pokédex field map](#6-the-pokédex-field-map)
- [7. The CP math](#7-the-cp-math)
- [8. Verification strategy](#8-verification-strategy)

---

## 1. The problem

`GAME_MASTER` is the file that defines Pokémon GO's *mechanics*: every Pokémon's
base stats, every move's power and energy, type effectiveness, CP formulas,
power-up costs, items, leagues, weather boosts, and so on. Niantic ships it to
the client as a **serialized protocol-buffers (protobuf) message**.

The catch: **Niantic does not publish the `.proto` schema**, and they reshuffle
field numbers with almost every client update. Older tools shipped a hand-written
`.proto` (or assumed the legacy JSON format) and therefore break whenever Niantic
changes the layout. Our goal is a decoder that **cannot go stale**.

## 2. A 5-minute primer on protobuf wire format

A protobuf message is just a flat sequence of **fields**. Each field is written
as a **tag** (a varint) followed by a payload. The tag packs two things:

```
tag = (field_number << 3) | wire_type
```

There are four wire types we care about:

| Wire type | Name  | Meaning                                   | How to read it |
|:---------:|-------|-------------------------------------------|----------------|
| `0`       | VARINT| int / bool / enum                         | read a varint |
| `1`       | I64   | fixed 64-bit (usually `double`)           | read 8 bytes |
| `2`       | LEN   | length-delimited: string, bytes, **sub-message**, or **packed repeated** | read a length varint, then that many bytes |
| `5`       | I32   | fixed 32-bit (usually `float`)            | read 4 bytes |

A **varint** is a little-endian base-128 integer: each byte contributes 7 bits,
and the high bit (`0x80`) means "more bytes follow". So `0x96 0x01` = `150`.

The critical observation for everything below: **the field number tells you
*which* field, but the wire type alone does not tell you the *meaning*.** A
`LEN` field could be a UTF-8 string, an opaque blob, a nested message, or a
"packed" array of numbers — all encoded identically. Hold that thought.

## 3. Schema-free decoding

`protobuf_decoder.py` walks the byte stream and decodes each field by wire type,
**without any schema**:

```python
from pogodecode.protobuf_decoder import decode_message
msg = decode_message(raw_bytes)   # -> {"1": "...", "2": {...}, "9": {...}}
```

The result is a dict keyed by the **field number as a string**, because Niantic
ships no field names. Values are typed by wire type:

- VARINT → `int`
- I64 → `float`, I32 → `float` (trimmed to ~7 significant digits for readable JSON)
- LEN → decoded heuristically (see §5): nested message (`dict`), `str`, or raw
  bytes as `{"__bytes__": "<base64>"}`.

This is the part that "cannot break": adding or moving a field just changes the
numbers that appear; nothing throws.

## 4. The GAME_MASTER layer

`gamemaster.py` knows the *outermost* shape of the file (and only that):

```
GameMaster { repeated Template templates = 2 }
Template   { string template_id = 1;  Data data = 2 }
```

The genuinely stable, useful information is the **`template_id`** — it's a plain
string stored in the file, e.g. `V0006_POKEMON_CHARIZARD`, `COMBAT_SETTINGS`,
`EXTENDED_V0001_POKEMON_BULBASAUR`. We read every template id exactly, and decode
each template's payload schema-free. The output is:

```jsonc
{
  "meta":          { "source": "...", "templateCount": 18707, ... },
  "templatesById": { "<id>": <decoded payload>, ... },   // fast lookup
  "templates":     [ { "templateId": "...", "data": {...} }, ... ], // file order
  "categories":    { "POKEMON": [...ids], "MOVE": [...ids], ... }    // by prefix
}
```

Because template ids are exact and stable, **any consumer can find the data it
wants by id**, even across client updates — only the numeric field layout
*inside* a template can shift.

## 5. The fundamental ambiguity (and how we resolve it)

Recall §2: a `LEN` field is used for strings, sub-messages, **and packed
repeated scalars**. A Pokémon's move list is a *packed repeated varint* — e.g.
Charizard's fast moves are stored as the bytes for `[209, 252]`. On the wire,
those bytes are **byte-for-byte indistinguishable from a small sub-message**.

The schema-free decoder has to guess. Its heuristic (in `_decode_length_delimited`):

1. If the bytes parse cleanly as a sub-message **and** aren't valid text → treat
   as a nested message.
2. Else if the bytes look like UTF-8 text → treat as a string.
3. Else → keep raw bytes as `{"__bytes__": ...}`.

For **most** move lists the bytes don't parse as a valid message, so they land
in case 3 and the Pokédex layer unpacks them. But for **some** Pokémon the move
bytes *happen* to parse as a valid message, and the guess is wrong. Real example:
**Dragonite's** fast-move bytes `[253, 239, 204]` parse as a bogus message
`{31: 7.49e-38}`, so the moves silently vanished. (~200 Pokémon were affected;
see [BUGS.md](BUGS.md#b1).)

You cannot fix this with a better *guess* — the ambiguity is fundamental. You
fix it with **schema knowledge applied at exactly the spots that need it.** The
decoder accepts an optional set of **field paths** that are known to be packed
scalars:

```python
# keep the bytes at path (2, 2, 9) raw instead of recursing into a "message"
decode_message(buf, packed_paths={(2, 2, 9)})
```

A *path* is the tuple of field numbers from the message root, so the hint is
surgical: it affects `data(2) → PokemonSettings(2) → quickMoves(9)` and nothing
else. The GAME_MASTER layer applies these hints **only to Pokémon templates**, so
the schema-free guarantee is preserved everywhere else:

```python
_POKEMON_PACKED_PATHS = {
    (2, 2, 9), (2, 2, 10),         # quick / charge moves
    (2, 2, 49), (2, 2, 50),        # elite (legacy) quick / charge moves
    (2, 2, 77),                    # Mega-required move (Rayquaza: Dragon Ascent)
    (2, 2, 63, 8, 2, 1),           # form-change signature move (Zacian, Keldeo, ...)
    (2, 2, 63, 8, 2, 2),
}
```

This is the single most important idea in the codebase: **stay schema-free by
default; inject the minimum schema knowledge, by path, only where the wire format
is genuinely ambiguous.**

## 6. The Pokédex field map

`pokedex.py` is a thin, **documented** map from numeric field numbers to human
meaning. It's deliberately small and every entry is a named constant:

```python
PF_STATS        = "8"    # {1: stamina, 2: attack, 3: defense}
PF_QUICK_MOVES  = "9"
PF_CHARGE_MOVES = "10"
PF_ELITE_QUICK  = "49"
PF_ELITE_CHARGE = "50"
PF_TEMP_EVO     = "51"   # Mega / Primal overrides (stats + typing)
PF_FORM_CHANGE  = "63"   # form-change settings (signature moves)
PF_MEGA_REQUIRED_MOVE = "77"
# ... etc.
```

It assembles a per-Pokémon **sheet** (see
[INTEGRATION.md](INTEGRATION.md#the-sheet-schema)) with names, stats, resolved
moves, type matchups, CP, costs, and so on. Move ids are resolved to names by
reading the move templates (`V####_MOVE_*` and `COMBAT_V####_MOVE_*`).

This is the only layer that carries "schema" knowledge, and it is the only layer
that needs maintenance if Niantic renumbers a field. When that happens you change
**one constant**, not a `.proto` file.

## 7. The CP math

Max CP for perfect IVs (15/15/15) is:

```
CP = floor( (Atk+15) * sqrt(Def+15) * sqrt(Sta+15) * CPM(level)^2 / 10 )
```

`CPM(level)` is the **CP multiplier**, a per-level constant stored in
`PLAYER_LEVEL_SETTINGS` as a packed `float` array. The single most common
mistake other tools make is indexing it wrong: the array is **integer-level
indexed** (`index = level - 1`), and the half-levels are interpolated. Using the
final array element for Level 50 (instead of `index = 49`) produces a ~6% CP
error. See [BUGS.md](BUGS.md#b2).

## 8. Verification strategy

A schema-free decoder is only trustworthy if its field map is checked against
ground truth. Two mechanisms:

1. **Reference values in the tests** — known-correct numbers are asserted against
   a real file, e.g. Bulbasaur `118/111/128` → Max CP `1115`; Mewtwo catch rate
   `2%`; Charizard L50 CP `3266`. If a field-map constant is wrong, a test fails.
2. **The `validate()` report** — a whole-file sanity sweep: Pokémon with no
   resolvable moves, unresolved move ids, stat/type outliers, zero-duration
   moves. This is what surfaced the Dragonite class of bug: "203 Pokémon with no
   fast move" was the symptom that pointed at the decoder.

If you adapt this project, keep both: reference assertions catch *wrong* mappings;
the validation sweep catches *missing* data.
