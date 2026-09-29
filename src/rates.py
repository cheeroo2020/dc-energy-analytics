"""Loading the rate configs, with an optional overlay of invented numbers.

The real configs in config/ ship with every published rate at 0.0 and
status: PLACEHOLDER. That is deliberate: a rate with no citation should not
quietly produce a dollar figure.

To run the pipeline before those rates have been downloaded, pass
variant="illustrative". That loads the same config files, then overlays the
invented numbers from config/illustrative/rates.yml and stamps each one
ILLUSTRATIVE_NOT_REAL, so the fake rate is visible on every output row it
touches.

There is only one copy of each config file. The overlay holds numbers only, so
the real and illustrative versions cannot drift apart structurally.
"""

from src.config import load_config, walk

OVERLAY_STATUS = "ILLUSTRATIVE_NOT_REAL"
OVERLAY_SOURCE = "Invented for demonstration. See config/illustrative/README.md."

RATE_FILES = ("network_tariff.yml", "retail_contract.yml", "factors.yml")


def match_entry(entries, key):
    """Pick one entry out of a config list by its code or financial year.

    Addressing list entries by name rather than by position means reordering a
    config file can never silently point an overlay at the wrong charge.
    """
    for entry in entries:
        if entry.get("code") == key or entry.get("financial_year") == key:
            return entry
    raise KeyError(f"No config list entry is identified by {key!r}")


def find_block(config, path):
    """Follow a dotted path to the {value, status, source} block it names.

    Dictionaries are indexed by key, lists by entry name, e.g.

        charges.NUOS_DEMAND.rate
        loss_factors.distribution_loss_factor.FY2025
        power_factor
    """
    node = config
    for segment in path.split("."):
        node = match_entry(node, segment) if isinstance(node, list) else node[segment]
    return node


def apply_overlay(config, overlay):
    """Write invented numbers into a loaded config, restamping their status."""
    for path, value in overlay.items():
        block = find_block(config, path)
        if not isinstance(block, dict) or "value" not in block:
            raise KeyError(f"Overlay path {path!r} does not point at a value block")
        block["value"] = value
        block["status"] = OVERLAY_STATUS
        block["source"] = OVERLAY_SOURCE
    return config


def load_rates(variant=None):
    """Load the network tariff, retail contract and loss factor configs.

    variant=None gives the real configs, with every published rate at 0.0.
    variant="illustrative" overlays the invented numbers on top.
    """
    configs = load_rate_configs(variant)
    return configs["network_tariff.yml"], configs["retail_contract.yml"], configs["factors.yml"]


def unsourced(configs):
    """Every number in the loaded rate configs still at PLACEHOLDER status.

    Returns a list of (config_name, dotted_path) pairs. A calculated bill is
    meaningless while this is non-empty, so callers should refuse to present a
    total rather than quietly publishing one built on zeros.

    This walks the whole config, not just the charge rates, so traps like a
    power factor left at its 1.0 default are caught too. A power factor of 1.0
    does not produce an obviously wrong zero - it silently understates every
    kVA demand charge, which is worse.
    """
    found = []
    for name, config in configs.items():
        for path, block in walk(config):
            if block.get("status") == "PLACEHOLDER":
                found.append((name, path))
    return found


def load_rate_configs(variant=None):
    """Same as load_rates, but keyed by filename so `unsourced` can name files."""
    configs = {name: load_config(name) for name in RATE_FILES}
    if variant:
        overlay = load_config(f"{variant}/rates.yml")
        unknown = set(overlay) - set(configs)
        if unknown:
            raise KeyError(f"Overlay names config files that do not exist: {sorted(unknown)}")
        for name, config in configs.items():
            apply_overlay(config, overlay.get(name) or {})
    return configs
