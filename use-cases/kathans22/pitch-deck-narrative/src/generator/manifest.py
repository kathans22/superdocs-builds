"""Load deck-manifest.yaml, product.yaml, and every vertical knowledge file.

Adding a vertical is a new YAML under config/verticals/ — zero code changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

REQUIRED_VERTICAL_FIELDS: tuple[str, ...] = (
    "vertical",
    "buyer_role",
    "regulatory_trigger",
    "document_pain",
    "typical_objection",
    "proof_point",
    "terminology",
)

ALLOWED_WEIGHTS: frozenset[str] = frozenset({"shared", "vertical"})


def project_root() -> Path:
    """use-cases/kathans22/pitch-deck-narrative/ (parent of src/)."""
    return Path(__file__).resolve().parents[2]


def config_dir(root: Path | None = None) -> Path:
    return (root or project_root()) / "config"


def _read_yaml(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if data is None:
        raise ValueError(f"config file is empty: {path}")
    return data


def load_deck_manifest(root: Path | None = None) -> dict[str, Any]:
    """Load config/deck-manifest.yaml."""
    path = config_dir(root) / "deck-manifest.yaml"
    data = _read_yaml(path)
    if not isinstance(data, dict):
        raise ValueError(f"deck manifest must be a mapping: {path}")
    return data


def load_product(root: Path | None = None) -> dict[str, Any]:
    """Load config/product.yaml."""
    path = config_dir(root) / "product.yaml"
    data = _read_yaml(path)
    if not isinstance(data, dict):
        raise ValueError(f"product config must be a mapping: {path}")
    return data


def load_verticals(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load every *.yaml under config/verticals/. Keyed by stem (e.g. legal)."""
    directory = config_dir(root) / "verticals"
    if not directory.is_dir():
        raise FileNotFoundError(f"verticals directory not found: {directory}")

    verticals: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.yaml")):
        data = _read_yaml(path)
        if not isinstance(data, dict):
            raise ValueError(f"vertical file must be a mapping: {path}")
        verticals[path.stem] = data
    return verticals


def load_all(root: Path | None = None) -> dict[str, Any]:
    """Load manifest, product, and all vertical files (no validation)."""
    return {
        "manifest": load_deck_manifest(root),
        "product": load_product(root),
        "verticals": load_verticals(root),
    }
