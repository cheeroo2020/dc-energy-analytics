# Illustrative rates - NOT REAL

Every number in this folder is **invented** so the pipeline can be run end to
end before the real published rates have been downloaded.

They are deliberately **round numbers** (8.0, 15.0, 1.05, 0.20) so that anyone
reading an output can tell at a glance that no real rate is involved. A real
network tariff rate is never 8.0000 c/kWh.

Every entry carries `status: ILLUSTRATIVE_NOT_REAL`, which flows all the way
through to `outputs/bill_lines.csv`, so each line of every calculated bill says
on its face that its rate is fake.

## How it is used

```bash
python -m src.tariff                        # uses config/ - real rates, all 0.0
python -m src.tariff --rates illustrative   # uses this folder
```

## How to stop using it

Work down `docs/DATA_SOURCES.md`, put real values into `config/*.yml`, change
each `status: PLACEHOLDER` to `status: SOURCED` with a citation, then drop the
`--rates illustrative` flag. Confirm with:

```bash
python -m src.check_placeholders
```

Do not copy these numbers into `config/`. That would destroy the only thing
separating a sourced figure from a guess.
