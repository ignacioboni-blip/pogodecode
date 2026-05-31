"""Command-line entry point: decode a GAME_MASTER file to JSON.

Usage::

    python -m pogodecode.cli GAME_MASTER -o game_master.json
    python -m pogodecode.cli GAME_MASTER --minify --stats
"""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__, write_json
from .gamemaster import decode_game_master
from .protobuf_decoder import ProtobufDecodeError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pogodecode",
        description="Decode a Pokemon GO GAME_MASTER protobuf file into JSON.",
    )
    parser.add_argument("input", help="path to the GAME_MASTER file")
    parser.add_argument(
        "-o", "--output",
        help="output JSON path (default: <input>.json)",
    )
    parser.add_argument(
        "--minify", action="store_true",
        help="write compact JSON instead of pretty-printed",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="print decode statistics to stderr",
    )
    parser.add_argument("--version", action="version", version=f"pogodecode {__version__}")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    output = args.output or (args.input + ".json")

    started = time.time()
    try:
        result = decode_game_master(args.input)
    except FileNotFoundError:
        print(f"error: file not found: {args.input}", file=sys.stderr)
        return 2
    except ProtobufDecodeError as exc:
        print(f"error: not a valid GAME_MASTER protobuf: {exc}", file=sys.stderr)
        return 1

    write_json(result, output, pretty=not args.minify)
    elapsed = time.time() - started

    meta = result["meta"]
    if args.stats:
        print(
            f"decoded {meta['templateCount']} templates "
            f"({meta['categoryCount']} categories, "
            f"{meta['skippedEntries']} skipped) "
            f"in {elapsed:.2f}s -> {output}",
            file=sys.stderr,
        )
    else:
        print(f"wrote {meta['templateCount']} templates to {output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
