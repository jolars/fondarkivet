"""Command-line interface for collecting and archiving fund NAVs."""

from argparse import ArgumentParser
from collections.abc import Sequence
from pathlib import Path

from .collector import fetch_quotes
from .output import build


def main(argv: Sequence[str] | None = None) -> None:
    parser = ArgumentParser(description="Collect fund NAVs and build the static API.")
    parser.add_argument("archive", type=Path, help="directory for historical NAV CSVs")
    parser.add_argument("site", type=Path, help="directory for the generated site")
    args = parser.parse_args(argv)

    quotes = fetch_quotes()
    build(quotes, args.archive, args.site)
