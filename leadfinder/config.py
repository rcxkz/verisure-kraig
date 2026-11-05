import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"


def load(path=None):
    path = Path(path) if path else ROOT / "config.toml"
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    cfg["towns"] = [t for t in cfg.get("towns", []) if t.get("include", True)]
    cfg.setdefault("exclusions", {}).setdefault("streets", [])
    cfg["exclusions"].setdefault("postcode_prefixes", [])
    return cfg
