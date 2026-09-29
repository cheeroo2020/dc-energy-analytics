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


def val(node):
    """Return the number held in a config entry.

    Entries that need a real published source are written as
    {"value": ..., "status": ..., "source": ...}. Plain numbers are written
    plainly. This accepts either and returns the number.
    """
    if isinstance(node, dict) and "value" in node:
        return node["value"]
    return node
