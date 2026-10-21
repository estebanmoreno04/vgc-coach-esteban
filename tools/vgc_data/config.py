"""Load the pipeline configuration from config/vgc-data.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "vgc-data.yaml"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: configuration must be a mapping")
    for section in ("game", "http", "paths", "resolver", "sources", "pipeline"):
        if not isinstance(payload.get(section), dict):
            raise ValueError(f"{path}: missing '{section}' section")
    return payload


def repo_path(config: dict[str, Any], key: str, *, root: Path = REPO_ROOT) -> Path:
    """Resolve a repository-relative path from the ``paths`` section."""
    return root / config["paths"][key]
