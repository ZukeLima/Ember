"""Load generator configuration and fixture profiles."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_generator_config(path: Path | None = None) -> dict[str, Any]:
    path = path or CONFIG_DIR / "generator.yml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_profile(name: str, config_dir: Path | None = None) -> dict[str, Any]:
    """Return the generator config for a fixture profile (clean, tiny, dirty…).

    The profile overrides `generator.yml`; `inject` lists the dirty cases to add.
    """
    config_dir = config_dir or CONFIG_DIR
    base = load_generator_config(config_dir / "generator.yml")
    with open(config_dir / "fixtures.yml", encoding="utf-8") as f:
        profiles = yaml.safe_load(f)["profiles"]
    if name not in profiles:
        raise KeyError(f"unknown fixture profile {name!r}; known: {sorted(profiles)}")
    profile = dict(profiles[name])
    inject = list(profile.pop("inject", []) or [])
    cfg = _deep_merge(base, profile)
    cfg["profile"] = name
    cfg["inject"] = inject
    return cfg
