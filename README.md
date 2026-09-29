# Data Centre Energy Analytics (simulated)

A self-directed learning project. It builds, from scratch, the core analytical
loop an energy analyst runs for a large electricity customer in the Australian
National Electricity Market (NEM):

**simulate interval data → price it → check the retailer's invoice → forecast it
forward → account for the certificates and emissions.**

All outputs are CSVs designed to be loaded straight into Power BI.

---

## Honesty statement (please read before judging any number)

- **Every input is invented.** There is no real site, customer, NMI, meter,
  retailer or invoice anywhere in this repository. The site is
  "Simulated Data Centre A" and its NMI is `SIMDC00001`, which is not a valid
  NMI format.
- **No real published rate is guessed at.** Network tariff rates, distribution
  and marginal loss factors, market fees, renewable certificate percentages and
  emission factors all ship as `0.0` with `status: PLACEHOLDER` and a note
  saying exactly which document to download. See
  [`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).
- **Simulation inputs are labelled separately** as `status: ASSUMPTION`. Those
  are *meant* to be invented — they are the made-up physics of the fake site.
- Run `python -m src.check_placeholders` at any time to see what is still
  unfilled. It also writes `outputs/placeholder_register.csv`, so the
  provenance of every number is visible in the Power BI report itself.
- The author has no professional experience in the energy industry. This is a
  study exercise built to learn the domain.

---

## Roadmap

| # | Piece | Module | Status |
|---|-------|--------|--------|
| 1 | Simulated half-hourly load + NEM12 read/write | `src/simulate_load.py`, `src/nem12.py` | ✅ built |
| 2 | Network + retail tariff engine | `src/tariff.py` | ⬜ |
| 3 | Monthly bill calculation | `src/billing.py` | ⬜ |
| 4 | Invoice checker with planted errors | `src/invoice_check.py` | ⬜ |
| 5 | Consumption forecast from the build schedule | `src/forecast.py` | ⬜ |
| 6 | LGC position + scope 2 emissions | `src/sustainability.py` | ⬜ |
| 7 | Power BI output pack | `src/export.py` | ⬜ |

---

## Quick start

```bash
cd ~/Projects/dc-energy-analytics
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m src.check_placeholders     # what still needs a real value
python -m src.simulate_load          # generate load + NEM12, verify round trip
```

---

## Layout

```
config/       Every input number, with its source recorded next to it
src/          The code. One module per step of the pipeline.
data/nem12/   Generated NEM12 files (the "raw data" the pipeline consumes)
data/invoices/ Generated invoices, some with deliberate errors
outputs/      Clean CSVs for Power BI
docs/         Which official documents to download, and why
```

## Key conventions

- **Interval length: 30 minutes**, so 48 intervals per day.
- **Intervals are labelled by their END time.** The first interval of 1 January
  covers 00:00–00:30 and is stamped `00:30`. This is the NEM convention.
- **Time is fixed AEST (UTC+10) with no daylight saving.** This is a deliberate
  simplification so that every day has exactly 48 intervals. Real metering data
  for a DST state needs checking against the AEMO MDFF specification — noted in
  `docs/DATA_SOURCES.md`.
- **Time-of-use periods are assigned using the interval START time.** Verify
  against your chosen network's tariff definition before trusting a bill.
- **Energy vs power:** `kWh = kW × 0.5` for a half-hour interval.
