"""List every config number that is still a placeholder.

Run it:

    python -m src.check_placeholders

It prints a report and writes outputs/placeholder_register.csv, so the Power BI
report can show the provenance of every number it displays.
"""

import pandas as pd

from src.config import ROOT, load_config


def walk(node, path=""):
    """Find every {value, status, source} block in a nested config.

    Yields (dotted_path, block). Recurses through dictionaries and lists until
    it hits a block that has both "value" and "status", which it treats as a
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
            yield from walk(child, f"{path}[{i}]")


def collect():
    """Walk every config file and return one row per tracked number."""
    rows = []
    for path in sorted((ROOT / "config").glob("*.yml")):
        config = load_config(path.name)
        for key, block in walk(config):
            rows.append(
                {
                    "file": path.name,
                    "setting": key,
                    "value": block.get("value"),
                    "status": block.get("status"),
                    "source": block.get("source", ""),
                }
            )
    return pd.DataFrame(rows)


def main():
    register = collect()
    if register.empty:
        print("No tracked numbers found in config/.")
        return

    out = ROOT / "outputs" / "placeholder_register.csv"
    register.to_csv(out, index=False)

    placeholders = register[register["status"] == "PLACEHOLDER"]
    assumptions = register[register["status"] == "ASSUMPTION"]

    print(f"{len(register)} tracked numbers across {register['file'].nunique()} config file(s)")
    print(f"  {len(placeholders)} PLACEHOLDER  (needs a real published value)")
    print(f"  {len(assumptions)} ASSUMPTION   (invented on purpose)")

    if len(placeholders):
        print("\nStill needing a real value:")
        for _, row in placeholders.iterrows():
            print(f"  {row['file']:<22} {row['setting']}")
            print(f"  {'':<22} -> {row['source']}")

    print(f"\nWritten: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
