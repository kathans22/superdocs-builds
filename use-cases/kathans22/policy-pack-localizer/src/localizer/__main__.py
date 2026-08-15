"""CLI entry point: python -m localizer run --countries IN [--limit N]."""

from __future__ import annotations

import argparse
import asyncio

from . import service


def _parse_countries(value: str) -> list[str]:
    return [code.strip() for code in value.split(",") if code.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m localizer")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Lock the core and generate a pack per country.")
    run_parser.add_argument("--countries", required=True, help="Comma-separated country codes, e.g. IN,KE")
    run_parser.add_argument("--limit", type=int, default=None, help="Process only the first N countries.")

    args = parser.parse_args(argv)

    if args.command == "run":
        countries = _parse_countries(args.countries)
        outcome = asyncio.run(service.run(countries, limit=args.limit))
        for code, result in outcome["results"].items():
            status = "SKIPPED" if result.get("skipped") else "OK"
            print(f"[{code}] {status}")
        print()
        outcome["ledger"].report()
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
