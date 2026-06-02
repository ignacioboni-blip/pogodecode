# Bugs, fixes, and limitations

An honest catalogue of what was wrong, what's fixed, what *could* still bite, and
what this tool fundamentally cannot do. If you rely on the output for anything
important, read this page.

- [Fixed bugs](#fixed-bugs)
- [Known limitations (by design)](#known-limitations-by-design)
- [Potential bugs (things to watch)](#potential-bugs-things-to-watch)
- [How to check for yourself](#how-to-check-for-yourself)

---

## Fixed bugs

### <a id="b1"></a>B1 — Silently dropped movepools (~200 Pokémon)

**Symptom.** Many Pokémon (e.g. **Dragonite**) showed *no* fast moves; the
`validate()` report counted 203 Pokémon "without a fast move."

**Cause.** A packed repeated varint (a move-id list) is wire-format-identical to
a sub-message. The schema-free decoder guessed "sub-message" for Pokémon whose
move bytes happened to parse as one — Dragonite's `[253, 239, 204]` decoded as a
bogus `{31: 7.49e-38}`, destroying the list. (See
[METHODOLOGY.md §5](METHODOLOGY.md#5-the-fundamental-ambiguity-and-how-we-resolve-it).)

**Fix.** Path-scoped decode hints (`packed_paths`) keep the known move fields as
raw bytes so the Pokédex layer can unpack them. False "no fast move" count went
**203 → 2** (only Smeargle, which legitimately has no fixed moves). Unresolved
move ids went to **0**.

### <a id="b2"></a>B2 — Level-50 CP off by ~6%

**Symptom.** Max CP at Level 50 disagreed with in-game values.

**Cause.** The CP-multiplier array was indexed with the wrong element for L50.
The array is **integer-level indexed** (`index = level - 1`), so L50 is index 49,
not the final element.

**Fix.** Correct integer-level indexing with half-level interpolation. Verified:
Charizard L40 `2889` / L50 `3266`; Mewtwo L40 `4178` / L50 `4724`.

### <a id="b3"></a>B3 — Elite / legacy moves not shown

**Symptom.** Moves obtainable only via Elite TM / Community Day / events (e.g.
Mewtwo's **Shadow Ball** & **Psystrike**, Poliwrath's **Counter**) were missing.

**Cause.** They live in separate fields (49 = elite fast, 50 = elite charged)
that the viewer never read.

**Fix.** Decoded and surfaced as their own "Elite/legacy" section; included in
`validate()` so elite-only movepools aren't mis-flagged as empty.

### <a id="b4"></a>B4 — Form / Mega signature moves not shown

**Symptom.** Moves a Pokémon only gets through a Mega or form change — **Mega
Rayquaza's Dragon Ascent**, **Crowned Zacian's Behemoth Blade**, **Crowned
Zamazenta's Behemoth Bash**, **Keldeo's Secret Sword** — didn't appear in any
move list.

**Cause.** These are stored outside the normal pools: field 77 (Mega-required
move) and the form-change struct field 63 (signature move at `63 → 8 → 2 → 1`),
again as packed varints subject to the B1 ambiguity.

**Fix.** Extended the decode hints to those paths and added a `requiredMoves`
section, filtered to moves not already in the fast/charge/elite pools (so normal
Pokémon show nothing).

## Known limitations (by design)

These are **not** bugs — the data simply isn't in `GAME_MASTER`, or is inherent
to schema-free decoding.

- **No spawn / raid / research data.** `GAME_MASTER` is a static config of game
  *mechanics*. "Found in the wild," raid bosses, egg pools, and research rewards
  are event-driven, server-side data Niantic rotates weekly. **No decoder can
  pull them from this file.** The only spawn-adjacent value present is gender
  ratio.
- **Field *names* are not in the file.** Only field *numbers* are. The Pokédex
  layer recovers names for the fields it maps; everything else stays numeric.
- **Field numbers can change.** When Niantic renumbers a setting, the schema-free
  decode still succeeds, but a mapped value in `pokedex.py` may need its constant
  updated. This is a one-line change, not a rewrite — and `validate()` plus the
  reference tests are designed to catch it.
- **Mewtwo has no Counter.** Worth stating because it comes up: Mewtwo does not
  learn Counter in the data (its fast moves are Confusion / Psycho Cut). That's
  correct, not a gap.
- **`requiredMoves` shows the form's *own* move only.** The form-change struct
  also references the *counterpart* form's move (sub-field 2) — e.g. base
  Necrozma references Sunsteel Strike, which it can't use unfused. We
  deliberately exclude those to avoid listing moves a form can't actually use.

## Potential bugs (things to watch)

Be appropriately skeptical of these areas:

- **New ambiguous packed fields.** If Niantic adds a new packed-scalar field on
  Pokémon that happens to parse as a message, it could mis-decode the same way B1
  did — until a `packed_paths` hint is added for it. The `validate()` sweep is
  your early warning.
- **Loading from a previously-exported JSON.** The decode hints are applied when
  decoding a *raw* `GAME_MASTER`. If you decode raw → JSON **without** this tool's
  hints and then load that JSON, deeply-nested packed fields (e.g. form-change
  moves) may already be mangled. Prefer loading the raw file, or export with this
  tool (which applies the hints).
- **Heuristic string vs. bytes.** A blob that is valid UTF-8 *and* a valid
  message is treated as text. This is right for template ids but could
  occasionally mislabel a short binary field elsewhere.
- **Float precision.** `float`/`double` values are trimmed to ~7 significant
  digits for readable JSON. If you need exact bit-for-bit floats, read the raw
  field yourself.
- **Type-effectiveness constants.** Multipliers are read from the file, but the
  18×18 chart assumes the standard type ordering; an unusual reorder by Niantic
  would need a re-check.

## How to check for yourself

```bash
# whole-file sanity sweep
python -m pogodecode.dexcli GAME_MASTER --validate

# spot-check any Pokémon against the game / a wiki
python -m pogodecode.dexcli GAME_MASTER --name DRAGONITE

# compare two GAME_MASTER versions to see exactly what changed
python -m pogodecode.dexcli OLD_GAME_MASTER --diff NEW_GAME_MASTER
```

If you find a discrepancy, the fastest triage is: does `validate()` flag it? Is
the field mapped in `pokedex.py`? Is the value packed (and therefore possibly
mis-decoded)? Open an issue with the template id and the expected value.
