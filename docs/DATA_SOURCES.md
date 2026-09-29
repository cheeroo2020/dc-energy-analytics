# Official documents to download

Every number in this project that would be real in a live model is a labelled
placeholder. This is the shopping list for replacing them.

**How to use this file:** work down it in order. Each entry names the publisher,
the document title, and what you take out of it. Search the publisher's own
site for the exact title rather than trusting a link — these documents are
re-issued annually and old links rot.

Deep links are deliberately omitted so nothing here is a guess.

---

## 1. The NEM12 file format itself

| | |
|---|---|
| **Publisher** | AEMO (Australian Energy Market Operator) — `aemo.com.au` |
| **Document** | *Meter Data File Format Specification NEM12 and NEM13* (usually called the **MDFF Spec**) |
| **What you take** | The authoritative field-by-field layout of the 100, 200, 300, 400, 500 and 900 records; the list of valid `UOM` codes; the valid quality method flags and reason codes. |

Check specifically:

- The exact field order in the **200** record, and what `NMIConfiguration`,
  `RegisterID` and `MDMDataStreamIdentifier` are allowed to contain.
- Whether `UpdateDateTime` and `MSATSLoadDateTime` are mandatory in your context.
- **How daylight saving is handled.** This project uses fixed AEST with no DST,
  so every day has exactly 48 intervals. Real data for NSW, VIC, SA, TAS or ACT
  has to deal with 46-interval and 50-interval days. Confirm the rule before
  claiming the reader is production-ready.
- The valid **NMI** format and its checksum digit. `SIMDC00001` in this project
  is deliberately invalid.

Supporting reading, same publisher: the **Metrology Procedure: Part A and
Part B**, and **National Electricity Rules Chapter 7** (metering) from the AEMC
(`aemc.gov.au`).

---

## 2. Network (distribution and transmission) tariff rates

| | |
|---|---|
| **Publisher** | The relevant Distribution Network Service Provider (DNSP), with approval from the AER (`aer.gov.au`) |
| **Documents** | (a) the DNSP's **Annual Pricing Proposal** for the financial year, (b) its **Tariff Schedule** / price list, (c) its **Tariff Structure Statement** approved by the AER |
| **What you take** | The tariff code that matches the site, and every component rate on it: fixed daily charge, time-of-use energy rates (c/kWh) with the exact clock times and season definitions, and demand charges ($/kVA/month or $/kW/month) with the exact definition of how the chargeable demand is measured. |

Pick the DNSP that matches wherever you decide the notional site is:

- **NSW** — Ausgrid, Endeavour Energy, Essential Energy
- **VIC** — CitiPower, Powercor, Jemena, United Energy, AusNet Services
- **QLD** — Energex, Ergon Energy
- **SA** — SA Power Networks
- **TAS** — TasNetworks
- **ACT** — Evoenergy

A data centre is a large customer, so look at the **HV / sub-transmission /
large business** tariffs, not the residential or small business ones.

Read very carefully, because this is where bills go wrong:

- Is the demand charge on **kW or kVA**? If kVA, you need a power factor
  assumption or metered reactive data.
- Is chargeable demand the **peak in the month**, or a **ratchet** that holds a
  historic peak for 12 months, or an average of the highest few intervals?
- Does the demand charge apply **only within a peak window** (e.g. weekday
  afternoons) or across all intervals?
- Are the rates quoted **excluding GST**? Almost always yes.

---

## 3. Loss factors

| | |
|---|---|
| **Publisher** | AEMO — look for the *Loss factors and regional boundaries* page |
| **Documents** | **Distribution Loss Factors (DLF)** for the financial year, and **Marginal Loss Factors (MLF)** for the financial year |
| **What you take** | The DLF for the site's distribution loss factor class, and the MLF for its transmission node. |

These are published annually and take effect **1 July**. They scale metered
consumption up to the volume settled in the wholesale market:

```
settled_volume = metered_kWh x DLF x MLF
```

Getting the financial-year boundary wrong is a classic invoice error, and one of
the errors this project plants deliberately.

---

## 4. Market fees and regulated pass-through charges

| | |
|---|---|
| **Publisher** | AEMO |
| **Documents** | AEMO's **Budget and Fees** publication and its **Fees and Charges** schedule for the financial year; the **ancillary services** (FCAS) recovery information |
| **What you take** | The NEM participant fee rates ($/MWh), the market ancillary service recovery rates, and any other regulated charges a retailer is entitled to pass through. |

Also relevant: any jurisdictional scheme charges for the state you choose
(for example NSW's **Energy Security Safeguard** / ESS, or VIC's **Victorian
Energy Upgrades** / VEU). Those are published by the state scheme administrator.

---

## 5. Renewable certificate obligations (the environmental charge lines)

| | |
|---|---|
| **Publisher** | Clean Energy Regulator (`cleanenergyregulator.gov.au`) |
| **Documents** | The **Renewable Power Percentage (RPP)** for the calendar year, and the **Small-scale Technology Percentage (STP)** for the calendar year |
| **What you take** | The two percentages, which set how many certificates a liable entity must surrender per MWh of liable acquisition. |

- **RPP** drives the Large-scale Renewable Energy Target (LRET) → **LGCs**
  (Large-scale Generation Certificates).
- **STP** drives the Small-scale Renewable Energy Scheme (SRES) → **STCs**
  (Small-scale Technology Certificates).

Both are set by legislative instrument each year, and both reset on the
**calendar** year, not the financial year — another boundary worth planting an
error on.

Also from the same publisher: the **REC Registry**, which is where LGCs are
created, transferred and surrendered, and the rules for **voluntary
surrender** — the mechanism behind a "100% renewable" claim.

For LGC **prices**: there is no single official price. Spot and forward prices
come from brokers and exchanges. Treat any price you use as a clearly labelled
market assumption, not an official figure.

---

## 6. Scope 2 emission factors

| | |
|---|---|
| **Publisher** | DCCEEW — Department of Climate Change, Energy, the Environment and Water (`dcceew.gov.au`) |
| **Document** | **Australian National Greenhouse Accounts Factors** (issued annually) |
| **What you take** | The **scope 2** electricity emission factor (kg CO2-e per kWh) for the state or territory you chose, and the **scope 3** factor for transmission and distribution losses plus extraction. |

Do not mix years, and do not mix states. The NSW factor and the TAS factor
differ by roughly an order of magnitude, which makes "which state is the site
in" one of the highest-leverage assumptions in the whole model.

Supporting documents:

- The **NGER (Measurement) Determination**, for how the factors are legally
  meant to be applied, from the Clean Energy Regulator.
- **GHG Protocol Scope 2 Guidance** (`ghgprotocol.org`) for the distinction
  between **location-based** and **market-based** reporting. A data centre
  operator making a renewable claim reports both, and the difference between the
  two numbers is the entire point of holding LGCs or a PPA.
- **AEMO's carbon dioxide equivalent intensity index (CDEII)** if you want
  half-hourly regional emissions intensity rather than one annual factor. This
  lets you show the emissions benefit of *when* load runs, not just how much.

---

## 7. Weather (only needed if you want a realistic load shape)

| | |
|---|---|
| **Publisher** | Bureau of Meteorology (`bom.gov.au`) |
| **Document** | **Climate Data Online** — daily and monthly observations by station |
| **What you take** | Monthly mean maximum and minimum temperature for the station nearest your notional site, to replace the invented sine-wave climate in `config/site.yml`. |

---

## 8. Data centre efficiency benchmarks (context, not calculation)

| | |
|---|---|
| **Publishers** | NABERS (`nabers.gov.au`); ISO/IEC |
| **Documents** | **NABERS Energy for Data Centres** rules and rating calculators; **ISO/IEC 30134-2** (Power Usage Effectiveness) |
| **What you take** | A defensible definition of PUE and the boundary it is measured across, so the PUE this project reports means something. |

---

## Filling in a placeholder

1. Find the number in the document.
2. Put it in the right `config/*.yml` entry.
3. Change `status: PLACEHOLDER` to `status: SOURCED`.
4. Replace `source:` with the document title, the edition or financial year, and
   the table or page number.
5. Re-run `python -m src.check_placeholders` to confirm it dropped off the list.

Step 4 is the one that matters. A rate with no citation is indistinguishable
from a rate somebody made up.
