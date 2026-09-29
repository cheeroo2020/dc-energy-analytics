"""Turn interval data into priced bill lines.

Four jobs, in order:

1. `assign_periods` labels every interval peak / shoulder / off peak, using the
   time-of-use rules from the network tariff config.
2. `loss_factors_for` finds the DLF and MLF that applied in a given month.
3. `summarise_month` boils a month of intervals down to the handful of numbers a
   bill actually needs: days, kWh in each period, peak demand, settled volume.
4. `charge_lines` applies every charge in the tariff to that summary and returns
   one row per bill line.

The output is long format - one row per (month, charge) - because that is what
Power BI wants and because it means a bill total is always a sum of visible
parts, never a number that appeared from nowhere.

Run it on one month as a demonstration:

    python -m src.tariff --rates illustrative
"""

import argparse

import pandas as pd

from src.config import ROOT, load_config, val
from src.rates import load_rate_configs, unsourced

CENTS_PER_DOLLAR = 100
KWH_PER_MWH = 1000


# ---------------------------------------------------------------------------
# 1. Time-of-use period assignment
# ---------------------------------------------------------------------------

def matches(rule, starts):
    """Which intervals match one time-of-use rule.

    A rule may filter on months, weekdays and an hour window. Any filter the
    rule leaves out is simply not applied, so a rule with no filters at all
    matches everything - that is how the catch-all off-peak rule works.
    """
    mask = pd.Series(True, index=starts.index)

    if "months" in rule:
        mask &= starts.dt.month.isin(rule["months"])
    if "weekdays" in rule:
        mask &= starts.dt.weekday.isin(rule["weekdays"])
    if "start_hour" in rule:
        hour = starts.dt.hour + starts.dt.minute / 60
        mask &= (hour >= rule["start_hour"]) & (hour < rule["end_hour"])

    return mask


def assign_periods(intervals, rules):
    """Label each interval with its time-of-use period. First rule wins.

    Uses the interval START time. An interval stamped 14:00 covers 13:30-14:00,
    so if peak begins at 14:00 that interval is NOT peak - the one stamped 14:30
    is the first peak interval.
    """
    period = pd.Series(pd.NA, index=intervals.index, dtype="object")
    starts = intervals["interval_start"]

    for rule in rules:
        unclaimed = period.isna() & matches(rule, starts)
        period[unclaimed] = rule["name"]

    if period.isna().any():
        raise ValueError(
            f"{period.isna().sum()} intervals matched no time-of-use rule. "
            "The last rule in config must be a catch-all with no filters."
        )
    return period


# ---------------------------------------------------------------------------
# 2. Loss factors
# ---------------------------------------------------------------------------

def loss_factors_for(month, factors):
    """The DLF and MLF that applied in a given month.

    Both are published annually by AEMO and take effect on 1 July. This takes
    the latest entry whose effective_from is on or before the month, so the
    financial-year boundary is handled explicitly rather than by accident.
    """
    def pick(entries, label):
        applicable = [e for e in entries if pd.Timestamp(e["effective_from"]) <= month]
        if not applicable:
            raise ValueError(f"No {label} is effective on or before {month:%Y-%m-%d}")
        latest = max(applicable, key=lambda e: pd.Timestamp(e["effective_from"]))
        return val(latest), latest["financial_year"]

    dlf, dlf_year = pick(factors["loss_factors"]["distribution_loss_factor"], "DLF")
    mlf, mlf_year = pick(factors["loss_factors"]["marginal_loss_factor"], "MLF")
    return {"dlf": dlf, "mlf": mlf, "dlf_year": dlf_year, "mlf_year": mlf_year}


# ---------------------------------------------------------------------------
# 3. Monthly summary
# ---------------------------------------------------------------------------

def summarise_month(intervals, factors, hours_per_interval=0.5):
    """Reduce one month of labelled intervals to the numbers a bill needs.

    `intervals` must already have a `period` column from assign_periods.
    """
    month = intervals["interval_start"].min().normalize().replace(day=1)
    losses = loss_factors_for(month, factors)

    metered_kwh = float(intervals["kwh"].sum())

    return {
        "month": month,
        "days": int(intervals["interval_start"].dt.normalize().nunique()),
        "metered_kwh": metered_kwh,
        # Loss factors scale metered consumption up to the volume settled in the
        # wholesale market. Charges billed per MWh use this, not the meter.
        "settled_mwh": metered_kwh * losses["dlf"] * losses["mlf"] / KWH_PER_MWH,
        "kwh_by_period": intervals.groupby("period")["kwh"].sum().to_dict(),
        "peak_kw_all": float(intervals["total_kw"].max()),
        "peak_kw_by_period": intervals.groupby("period")["total_kw"].max().to_dict(),
        **losses,
    }


# ---------------------------------------------------------------------------
# 4. Pricing
# ---------------------------------------------------------------------------

def charge_amount(charge, summary, power_factor):
    """Work out (quantity, unit, rate, amount) for one charge in one month.

    Six bases, matching how an Australian electricity bill is actually built up.
    """
    basis = charge["basis"]

    if basis == "fixed_daily":
        rate = val(charge["rate"])
        return summary["days"], "days", rate, rate * summary["days"]

    if basis == "fixed_monthly":
        rate = val(charge["rate"])
        return 1, "months", rate, rate

    if basis == "energy":
        # Rates are quoted in c/kWh, so divide by 100 to get dollars.
        rate = val(charge["rate"])
        period = charge.get("period")
        kwh = summary["kwh_by_period"].get(period, 0.0) if period else summary["metered_kwh"]
        return kwh, "kWh", rate, kwh * rate / CENTS_PER_DOLLAR

    if basis == "volume":
        # Rates in $/MWh apply to settled volume, i.e. after loss factors.
        rate = val(charge["rate"])
        mwh = summary["settled_mwh"]
        return mwh, "MWh", rate, mwh * rate

    if basis == "demand":
        # Billed on the single highest interval in the month, optionally only
        # within one time-of-use window.
        rate = val(charge["rate"])
        window = charge.get("window")
        peak_kw = summary["peak_kw_by_period"].get(window, 0.0) if window else summary["peak_kw_all"]

        if charge.get("measure", "kw").lower() == "kva":
            # Apparent power. A lagging power factor makes kVA larger than kW,
            # so assuming 1.0 understates a kVA demand charge.
            return peak_kw / power_factor, "kVA", rate, (peak_kw / power_factor) * rate

        return peak_kw, "kW", rate, peak_kw * rate

    if basis == "certificate":
        # The liable entity surrenders a percentage of its liable volume as
        # certificates. Quantity is certificates, the rate is their price.
        percentage = val(charge["percentage"])
        price = val(charge["price"])
        certificates = summary["settled_mwh"] * percentage
        return certificates, charge["certificate_unit"], price, certificates * price

    raise ValueError(f"Unknown charge basis: {basis!r}")


def rate_status(charge):
    """Whether this charge's rate is sourced, invented, or still a placeholder.

    Carried onto every bill line so no dollar figure can hide where it came
    from. A certificate charge is priced by its `price` block, not its `rate`.
    """
    block = charge.get("price") if charge["basis"] == "certificate" else charge.get("rate")
    return block.get("status", "UNKNOWN") if isinstance(block, dict) else "UNKNOWN"


def charge_lines(summary, charges, power_factor):
    """Price every charge for one month. Returns one row per bill line."""
    rows = []
    for charge in charges:
        quantity, unit, rate, amount = charge_amount(charge, summary, power_factor)
        rows.append(
            {
                "month": summary["month"],
                "code": charge["code"],
                "description": charge["description"],
                "category": charge["category"],
                "basis": charge["basis"],
                "quantity": round(quantity, 3),
                "quantity_unit": unit,
                "rate": rate,
                "rate_unit": charge["rate_unit"],
                "amount_ex_gst": round(amount, 2),
                "rate_status": rate_status(charge),
            }
        )
    return pd.DataFrame(rows)


def price_month(intervals, network, retail, factors):
    """Price one month of intervals against the network tariff and the contract."""
    summary = summarise_month(intervals, factors)
    power_factor = val(network["power_factor"])
    return summary, pd.concat(
        [
            charge_lines(summary, network["charges"], power_factor),
            charge_lines(summary, retail["charges"], power_factor),
        ],
        ignore_index=True,
    )


# ---------------------------------------------------------------------------
# Demonstration: price a single month
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Price one month of intervals.")
    parser.add_argument("--rates", default=None, choices=["illustrative"],
                        help="use invented rates so the pipeline runs before real rates are sourced")
    parser.add_argument("--month", default="2025-02", help="month to price, as YYYY-MM")
    parser.add_argument("--allow-placeholders", action="store_true",
                        help="show money even though some rates are still 0.0 placeholders")
    args = parser.parse_args()

    configs = load_rate_configs(args.rates)
    network = configs["network_tariff.yml"]
    retail = configs["retail_contract.yml"]
    factors = configs["factors.yml"]
    missing = unsourced(configs)
    site = load_config("site.yml")

    intervals = pd.read_csv(
        ROOT / "outputs" / "interval_load.csv", parse_dates=["interval_start", "interval_end"]
    )
    intervals["period"] = assign_periods(intervals, network["periods"])

    wanted = intervals["interval_start"].dt.strftime("%Y-%m") == args.month
    month_intervals = intervals[wanted].copy()
    if month_intervals.empty:
        raise SystemExit(f"No intervals found for {args.month}")

    summary, lines = price_month(month_intervals, network, retail, factors)
    gst_rate = val(factors["tax"]["gst_rate"])
    subtotal = lines["amount_ex_gst"].sum()

    print(f"{site['site']['name']}  ({site['site']['nmi']})")
    print(f"Billing month: {summary['month']:%B %Y}   {summary['days']} days")
    print(f"Rates:         {args.rates or 'config/ (real, unsourced)'}")
    print()
    print(f"Metered consumption   {summary['metered_kwh']:>12,.0f} kWh")
    print(f"DLF x MLF             {summary['dlf']:>12.3f} x {summary['mlf']:.3f}"
          f"   ({summary['dlf_year']} / {summary['mlf_year']})")
    print(f"Settled volume        {summary['settled_mwh']:>12,.1f} MWh")
    print(f"Peak demand (all)     {summary['peak_kw_all']:>12,.0f} kW")
    print()
    print("Consumption by time-of-use period:")
    for name, kwh in sorted(summary["kwh_by_period"].items(), key=lambda kv: -kv[1]):
        share = kwh / summary["metered_kwh"]
        peak_kw = summary["peak_kw_by_period"][name]
        print(f"  {name:<10} {kwh:>12,.0f} kWh  {share:>6.1%}   peak {peak_kw:>7,.0f} kW")
    print()

    show = lines[["code", "quantity", "quantity_unit", "rate", "rate_unit", "amount_ex_gst", "rate_status"]]
    print(show.to_string(index=False))
    print()

    # A bill built partly on 0.0 placeholders still adds up to a plausible
    # looking number, which is the most dangerous output this project could
    # produce. Refuse to present a total until every rate has a source.
    if missing and not args.allow_placeholders:
        print("=" * 72)
        print(f"NO TOTAL SHOWN: {len(missing)} rate(s) are still 0.0 PLACEHOLDER.")
        print("Any total would be a real number built on unsourced zeros.")
        print()
        for name, path in missing[:6]:
            print(f"  {name:<22} {path}")
        if len(missing) > 6:
            print(f"  ... and {len(missing) - 6} more")
        print()
        print("Fill them from docs/DATA_SOURCES.md, or run with:")
        print("  --rates illustrative     invented numbers, clearly labelled")
        print("  --allow-placeholders     show the total anyway (testing only)")
        print("=" * 72)
        return

    print(f"{'Subtotal (ex GST)':<28} {subtotal:>14,.2f}")
    print(f"{'GST at ' + format(gst_rate, '.0%'):<28} {subtotal * gst_rate:>14,.2f}")
    print(f"{'TOTAL (inc GST)':<28} {subtotal * (1 + gst_rate):>14,.2f}")
    if subtotal:
        print(f"\nAll-in cost: {subtotal / summary['metered_kwh'] * 100:.2f} c/kWh ex GST")
    if missing:
        print(f"\nWARNING: {len(missing)} rate(s) are still 0.0 placeholders. "
              "This total is not a bill.")


if __name__ == "__main__":
    main()
