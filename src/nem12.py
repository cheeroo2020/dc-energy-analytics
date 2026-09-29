"""Write and read AEMO's NEM12 interval metering format.

NEM12 is a flat CSV with no header row. Instead, the first field on every line
is a record indicator that says what kind of line it is:

    100   file header: format, when it was created, who sent it, who gets it
    200   which NMI / meter / unit / interval length the following data is for
    300   one calendar day of interval values for that meter, plus a data
          quality flag
    400   a note that only part of a day has a different quality (not used here)
    500   business-to-business settlement detail (not used here)
    900   end of file

A file can hold many 200 blocks, each followed by many 300 lines. This module
writes the 100 / 200 / 300 / 900 subset and reads it back.

IMPORTANT: the field order and the allowed values below are this project's
reading of the format. Before trusting them, check them line by line against
AEMO's "Meter Data File Format Specification NEM12/NEM13" (the MDFF Spec).
See docs/DATA_SOURCES.md.
"""

import pandas as pd

MINUTES_PER_DAY = 24 * 60

# Quality method flag on a 300 record. "A" means every interval in the day is
# an actual meter reading. Real files also carry "S" (substituted), "E"
# (estimated) and "F" (final substituted), each with a reason code. Handling
# those properly is what makes real metering data messy.
QUALITY_ACTUAL = "A"


def header_100(generated_at, from_participant, to_participant):
    """The file header record."""
    return f"100,NEM12,{generated_at:%Y%m%d%H%M},{from_participant},{to_participant}"


def details_200(site):
    """The meter details record: everything the 300 lines that follow apply to."""
    suffix = site["nmi_suffix"]
    return ",".join(
        [
            "200",
            site["nmi"],
            suffix,                            # NMI configuration
            "1",                               # register ID
            suffix,                            # NMI suffix: E1 = consumption
            "N1",                              # MDM data stream identifier
            site["meter_serial"],
            "KWH",                             # unit of measure
            str(site["interval_minutes"]),
            "",                                # next scheduled read date: unknown
        ]
    )


def day_300(day, values, updated_at, quality=QUALITY_ACTUAL, decimals=3):
    """One day of interval values.

    `values` must hold exactly one reading per interval in the day: 48 of them
    at 30-minute intervals.
    """
    readings = [f"{v:.{decimals}f}" for v in values]
    return ",".join(
        [
            "300",
            f"{day:%Y%m%d}",
            *readings,
            quality,
            "",                                # reason code
            "",                                # reason description
            f"{updated_at:%Y%m%d%H%M%S}",      # update datetime
            "",                                # MSATS load datetime
        ]
    )


def write_nem12(
    table,
    site,
    path,
    from_participant="SIMRETAIL",
    to_participant="SIMDC",
    generated_at=None,
):
    """Write one NMI's interval data to a NEM12 file.

    `table` needs an `interval_start` column and a `kwh` column. Intervals are
    grouped into days by their START time, because the interval stamped 00:00
    on 2 January actually belongs to 1 January.
    """
    minutes = site["interval_minutes"]
    expected_per_day = MINUTES_PER_DAY // minutes
    generated_at = generated_at or pd.Timestamp("2026-01-01 00:00")

    lines = [
        header_100(generated_at, from_participant, to_participant),
        details_200(site),
    ]

    for day, group in table.groupby(table["interval_start"].dt.normalize(), sort=True):
        group = group.sort_values("interval_start")
        if len(group) != expected_per_day:
            raise ValueError(
                f"{day:%Y-%m-%d} has {len(group)} intervals, expected {expected_per_day}"
            )
        lines.append(day_300(day, group["kwh"].tolist(), generated_at))

    lines.append("900")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    return path


def read_nem12(path):
    """Parse a NEM12 file into a tidy table: one row per interval.

    Returns columns: nmi, nmi_suffix, interval_start, interval_end, kwh,
    quality_method. This is the shape everything downstream expects.
    """
    rows = []
    nmi = None
    suffix = None
    minutes = None

    with open(path) as f:
        for line in f:
            fields = line.strip().split(",")
            record = fields[0]

            if record == "200":
                nmi = fields[1]
                suffix = fields[4]
                minutes = int(fields[8])

            elif record == "300":
                if minutes is None:
                    raise ValueError("Found a 300 record before any 200 record")

                day = pd.Timestamp(fields[1])
                count = MINUTES_PER_DAY // minutes
                readings = [float(v) for v in fields[2 : 2 + count]]
                quality = fields[2 + count]

                for i, kwh in enumerate(readings):
                    start = day + pd.Timedelta(minutes=i * minutes)
                    rows.append(
                        {
                            "nmi": nmi,
                            "nmi_suffix": suffix,
                            "interval_start": start,
                            "interval_end": start + pd.Timedelta(minutes=minutes),
                            "kwh": kwh,
                            "quality_method": quality,
                        }
                    )

    return pd.DataFrame(rows)
