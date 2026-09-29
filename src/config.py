"""Reading the config files, and pulling numbers out of them.

There are only two ideas in this module.

1. `load_config` reads one YAML file from config/ into a plain dictionary.
2. `val` unwraps the {value, status, source} blocks the configs use to record
   where a number is supposed to have come from.

Everything else in the project imports these two.
"""

from pathlib import Path

import yaml

# The project root: this file is src/config.py, so go up two levels.
ROOT = Path(__file__).resolve().parents[1]


def load_config(name):
    """Read config/<name> and return it as a dictionary."""
    path = ROOT / "config" / name
    with open(path) as f:
        return yaml.safe_load(f)


def walk(node, path=""):
    """Find every {value, status, source} block in a nested config.

    Yields (dotted_path, block). Recurses through dictionaries and lists until
    it reaches a block holding both "value" and "status", which it treats as a
    leaf and does not descend into.
    """
    if isinstance(node, dict):
        if "value" in node and "status" in node:
            yield path, node
            return
        for key, child in node.items():
            yield from walk(child, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for i, child in enumerate(node):
            # Name a list entry by its code or financial year where it has one,
            # rather than by position. Paths then survive a config being
            # reordered, and they read the same as the keys in
            # config/illustrative/rates.yml.
            label = None
            if isinstance(child, dict):
                label = child.get("code") or child.get("financial_year")
            step = str(label) if label else f"[{i}]"
            joiner = "." if (path and label) else ""
            yield from walk(child, f"{path}{joiner}{step}" if path else step)


def val(node):
    """Return the number held in a config entry.

    Entries that need a real published source are written as
    {"value": ..., "status": ..., "source": ...}. Plain numbers are written
    plainly. This accepts either and returns the number.
    """
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    return node
