# Legal notices & disclaimers

> **Not legal advice.** This document explains the project's intent and the steps
> it takes to respect others' rights. It is not legal advice. If you redistribute
> this software, host it publicly, or build a product on it, understand your own
> obligations.

## 1. No affiliation or endorsement

**pogodecode is an unofficial, fan-made, non-commercial project.** It is **not**
created, sponsored, endorsed by, affiliated with, or in any way officially
connected to:

- **Niantic, Inc.**
- **Nintendo Co., Ltd.**
- **The Pokémon Company**
- **Game Freak** or **Creatures Inc.**

…or any of their subsidiaries or affiliates.

## 2. Trademarks

**Pokémon**, **Pokémon GO**, **Niantic**, **Nintendo**, and all related names,
logos, characters, and marks are trademarks of their respective owners. They are
used here **only nominatively** — i.e. to accurately describe what this tool
interoperates with — which is a recognized fair use of trademarks. No claim of
ownership over any of these marks is made or implied. All rights in those marks
remain with their respective holders.

## 3. No game assets or copyrighted content are distributed

This repository and its releases **contain no Pokémon GO game data, art, audio,
or other copyrighted assets**, and **no `GAME_MASTER` file**. The software is a
**format decoder only**: it operates on a `GAME_MASTER` file that **the user
already possesses on their own device**. You must supply your own input file; the
project neither provides one nor tells you to obtain one unlawfully.

The decoded *factual data* (numeric stats, costs, durations) consists largely of
unprotectable facts; this tool merely re-expresses, for interoperability and
analysis, data the user already has. The project takes no position encouraging
infringement and distributes none of the underlying content.

## 4. Purpose: interoperability, analysis, and education

The project exists for **interoperability, data analysis, research, and
educational purposes** — understanding a public binary format and making one's
own data readable. Reverse-engineering a file format for interoperability is a
long-standing, widely-recognized legitimate activity.

## 5. Your responsibilities (acceptable use)

By using this software you agree that:

- You will **obtain any `GAME_MASTER` file lawfully** and only use files you are
  entitled to access.
- You are **solely responsible** for complying with **Niantic's Terms of Service**
  and any other applicable agreements, laws, and regulations in your
  jurisdiction. Extracting game files and operating third-party services may
  violate those Terms; that risk is yours to evaluate and accept.
- You will **not** use this project for cheating, spoofing, scraping live game
  servers, or any activity that harms the game or its players. This tool decodes
  a static config file — it does **not** interact with Niantic's servers — and it
  must not be used as part of anything that does so abusively.

## 6. No warranty / limitation of liability

The software is provided **"AS IS", without warranty of any kind**, as stated in
the [MIT License](../LICENSE). The decoded output **may be incomplete or
incorrect** (see [BUGS.md](BUGS.md)); do not rely on it for any
safety-, financial-, or legally-significant decision. To the maximum extent
permitted by law, the authors and contributors are **not liable** for any claim,
damages, or other liability arising from the software or its use.

## 7. Third-party components

- **Bundled fonts** — *Google Sans Flex* and *Quicksand* are included under the
  **SIL Open Font License 1.1**. Their license texts ship alongside them in
  [`pogodecode/assets/fonts/`](../pogodecode/assets/fonts/). The OFL permits
  bundling and redistribution; the fonts are not sold and are not the reserved
  name of this project.

See [NOTICE](../NOTICE) for the consolidated attribution list.

## 8. Rights holders — takedown / contact

This project respects intellectual-property rights and **will act promptly on
good-faith requests.** If you are a rights holder (or their authorized agent) and
believe something here infringes your rights or oversteps fair/nominative use:

1. **Open an issue** titled `LEGAL / takedown request`, or contact the maintainer
   listed on the repository, with the specifics (URL, file, and the concern).
2. The maintainer will **review and respond promptly**, and will remove or amend
   the material in question where appropriate while the matter is assessed.

The goal is good-faith cooperation, not confrontation. If Niantic, Nintendo, The
Pokémon Company, or any rights holder requests changes, the maintainer intends to
comply.

## 9. Changes

These notices may be updated over time; the version in the repository's default
branch governs. Material changes will be noted in [CHANGELOG.md](../CHANGELOG.md).
