"""Load the lab config. Any mode other than paper is rejected."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def repo_root() -> Path:
    candidates = [Path.cwd(), *Path(__file__).resolve().parents]
    for parent in candidates:
        if (parent / "research" / "results").is_dir() and (parent / "config.yaml").is_file():
            return parent
    return ROOT


def artifacts_dir() -> Path:
    path = repo_root() / "research" / "results"
    if not path.is_dir():
        raise FileNotFoundError(f"missing study artifacts at {path}")
    return path


def load_config(path: str | Path | None = None) -> dict:
    cfg_path = Path(path) if path else repo_root() / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    if not isinstance(cfg, dict):
        raise SystemExit("config.yaml must be a mapping")
    mode = str(cfg.get("mode", "")).strip().lower()
    if mode != "paper":
        raise SystemExit("Only paper mode exists. Live trading is not implemented.")
    return cfg
