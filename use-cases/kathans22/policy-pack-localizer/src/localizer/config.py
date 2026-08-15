"""Loads and validates manifest.yaml and country config files."""

from __future__ import annotations

from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"
MANIFEST_PATH = CONFIG_DIR / "manifest.yaml"
COUNTRIES_DIR = CONFIG_DIR / "countries"


def load_manifest(path: Path = MANIFEST_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_country(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_all_countries(directory: Path = COUNTRIES_DIR) -> dict:
    countries = {}
    for path in sorted(directory.glob("*.yaml")):
        country = load_country(path)
        countries[country["code"]] = country
    return countries
