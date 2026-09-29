"""Build a synthetic half-hourly electricity load for the simulated data centre.

The whole model is one line:

    total_kW = IT_kW * (1 + cooling_overhead + ups_loss) + fixed_auxiliary_kW

where

  * IT_kW comes from the build schedule: each data hall ramps up after it
    energises, and IT load is close to flat once it is running.
  * cooling_overhead grows with ambient temperature.
  * ambient temperature is two sine waves, one annual and one daily.

That is deliberately crude. The point is not weather modelling; it is to
produce a load shape with a summer-afternoon peak and a rising trend, because
those two features are what actually drive an Australian network bill.

Run it:

    python -m src.simulate_load
"""

import numpy as np
import pandas as pd

from src.config import ROOT, load_config, val
from src.nem12 import read_nem12, write_nem12

MINUTES_PER_HOUR = 60


def interval_index(start, end, minutes):
    """Half-hourly timestamps labelled by the END of each interval.

    NEM interval data is labelled by interval end: the first interval of
    1 January covers 00:00-00:30 and is stamped 00:30. The last interval of
    31 December is stamped 00:00 on 1 January.
    """
    first_end = pd.Timestamp(start) + pd.Timedelta(minutes=minutes)
    last_end = pd.Timestamp(end) + pd.Timedelta(days=1)
    return pd.date_range(first_end, last_end, freq=f"{minutes}min")


def hour_of_day(index):
    """Position within the day as a decimal hour, e.g. 14:30 -> 14.5."""
    return index.hour + index.minute / MINUTES_PER_HOUR


def ramp_fraction(index, energised, ramp_days):
    """How much of a hall's IT load is live at each timestamp.

    0 before it energises, rising in a straight line to 1 over ramp_days,
    then staying at 1.
    """
    days_since = (index - pd.Timestamp(energised)) / pd.Timedelta(days=1)
    return np.clip(days_since / max(ramp_days, 1), 0.0, 1.0)


def installed_it_load_kw(index, build_schedule):
    """Total IT load available at each timestamp, summed over all halls.

    This is the deterministic part: no noise, no daily swing. The forecast
    module reuses it unchanged, which is the point of keeping it separate.
    """
    total = np.zeros(len(index))
    for hall in build_schedule:
        total = total + val(hall["full_it_load_kw"]) * ramp_fraction(
            index, hall["energised"], hall["ramp_days"]
        )
    return pd.Series(total, index=index)


def it_load_kw(index, build_schedule, it_config, rng=None):
    """IT load: halls ramping up, plus a small daily swing, plus jitter.

    Pass rng=None to get the smooth expected shape with no random noise.
    The forecast does exactly that; the "actuals" pass a real generator.
    """
    installed = installed_it_load_kw(index, build_schedule)

    swing = 1 + it_config["diurnal_swing_fraction"] * np.cos(
        2 * np.pi * (hour_of_day(index) - it_config["peak_hour"]) / 24
    )
    load = installed * swing

    if rng is not None and it_config.get("random_noise_fraction"):
        jitter = rng.normal(0, it_config["random_noise_fraction"], len(index))
        load = load * (1 + jitter)

    return load


def ambient_temp_c(index, climate, rng=None):
    """Ambient temperature as an annual sine wave plus a daily sine wave.

    Southern hemisphere: the annual peak sits in January, set by
    hottest_day_of_year.
    """
    day_of_year = index.dayofyear + hour_of_day(index) / 24

    annual = val(climate["annual_amplitude_c"]) * np.cos(
        2 * np.pi * (day_of_year - climate["hottest_day_of_year"]) / 365.25
    )
    daily = val(climate["daily_amplitude_c"]) * np.cos(
        2 * np.pi * (hour_of_day(index) - climate["hottest_hour"]) / 24
    )
    temp = val(climate["annual_mean_temp_c"]) + annual + daily

    if rng is not None and climate.get("random_noise_c"):
        temp = temp + rng.normal(0, climate["random_noise_c"], len(index))

    return pd.Series(temp, index=index)


def cooling_overhead(temp_c, cooling_config):
    """Cooling load as a fraction of IT load.

    A flat base, plus a slope that only bites once it is warmer than the
    reference temperature.
    """
    excess_degrees = np.clip(temp_c - cooling_config["reference_temp_c"], 0, None)
    return val(cooling_config["base_fraction"]) + val(
        cooling_config["temp_slope_per_degc"]
    ) * excess_degrees


def build_interval_table(config, add_noise=True):
    """Assemble the full half-hourly table for the configured period."""
    site = config["site"]
    minutes = site["interval_minutes"]
    hours_per_interval = minutes / MINUTES_PER_HOUR

    index = interval_index(config["period"]["start"], config["period"]["end"], minutes)
    rng = np.random.default_rng(config["random_seed"]) if add_noise else None

    it_kw = it_load_kw(index, config["build_schedule"], config["it_load"], rng)
    temp_c = ambient_temp_c(index, config["climate"], rng)

    cooling_kw = it_kw * cooling_overhead(temp_c, config["cooling"])
    ups_kw = it_kw * config["auxiliary"]["ups_loss_fraction"]
    aux_kw = config["auxiliary"]["fixed_kw"]

    total_kw = it_kw + cooling_kw + ups_kw + aux_kw

    table = pd.DataFrame(
        {
            "interval_end": index,
            "interval_start": index - pd.Timedelta(minutes=minutes),
            "temp_c": temp_c.to_numpy().round(2),
            "it_kw": it_kw.to_numpy().round(3),
            "cooling_kw": cooling_kw.to_numpy().round(3),
            "ups_kw": ups_kw.to_numpy().round(3),
            "aux_kw": aux_kw,
            "total_kw": total_kw.to_numpy().round(3),
        }
    )
    table["kwh"] = (table["total_kw"] * hours_per_interval).round(3)

    # Power Usage Effectiveness: total site energy divided by IT energy. The
    # headline efficiency metric for a data centre. Guard against dividing by
    # zero before any hall has energised.
    table["pue"] = np.where(
        table["it_kw"] > 0, (table["total_kw"] / table["it_kw"]).round(3), np.nan
    )

    return table


def main():
    config = load_config("site.yml")
    site = config["site"]

    table = build_interval_table(config, add_noise=True)

    load_csv = ROOT / "outputs" / "interval_load.csv"
    table.to_csv(load_csv, index=False)

    nem12_path = (
        ROOT / "data" / "nem12" / f"{site['nmi']}_{config['period']['start']}"
        f"_{config['period']['end']}.csv"
    )
    write_nem12(table, site, nem12_path)

    # Read our own NEM12 file back and confirm it survived the trip. If the
    # writer and the reader ever disagree, this is where it shows up.
    recovered = read_nem12(nem12_path)
    matched = len(recovered) == len(table)
    if matched:
        difference = (
            recovered["kwh"].to_numpy() - table["kwh"].to_numpy()
        )
        matched = bool(np.abs(difference).max() < 1e-6)

    days = table["interval_start"].dt.normalize().nunique()
    print(f"Site:      {site['name']} ({site['nmi']})")
    print(f"Period:    {config['period']['start']} to {config['period']['end']}  ({days} days)")
    print(f"Intervals: {len(table):,} at {site['interval_minutes']} minutes")
    print(f"Peak kW:   {table['total_kw'].max():,.0f}")
    print(f"Total MWh: {table['kwh'].sum() / 1000:,.1f}")
    print(f"Mean PUE:  {table['pue'].mean():.3f}")
    print()
    print(f"Written: {load_csv.relative_to(ROOT)}")
    print(f"Written: {nem12_path.relative_to(ROOT)}")
    print(f"NEM12 round trip: {'PASS' if matched else 'FAIL'}")


if __name__ == "__main__":
    main()
