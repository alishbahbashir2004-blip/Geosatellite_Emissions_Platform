# CO2: why this folder does not look like the other four

The other four gases are the same program with different constants. CO2 is
not, and this file records why, with the numbers that settled it. Everything
quoted here is reproduced by `python -m co2.explore`.

## 1. It is a different instrument, for a reason

CH4, CO, NO2 and SO2 all come off **one** instrument: TROPOMI, on Sentinel-5P.
It is a push-broom imaging spectrometer with a **2600 km swath** — it images a
wide strip under the orbit, the strips overlap, and you get the whole planet
every day as a grid. That is why Earth Engine can hand you an `ImageCollection`
and why `reduceRegion` is a sensible thing to do to it.

CO2 comes off **OCO-2 / OCO-3**, and Earth Engine does not carry it at all.
The only CO2 in the EE catalog is `COPERNICUS/MARINE/.../CO2`, which is
dissolved CO2 in seawater. OCO-2's swath is **about 10 km** — 260x narrower.
It is a line, not a strip, and the 16-day repeat retraces the same lines, so
the ground between them is never sampled.

That trade was deliberate. See §2.

## 2. The reason for the trade: CO2 has no contrast

Every one of these gases is measured the same way — sunlight reflects off the
ground, the gas absorbs specific wavelengths on the way up, and the depth of
those absorption lines gives the amount of gas in the column. The difference
is not how you measure it. It is **how much of what you measure is the thing
you care about.**

| | atmospheric lifetime | background | a city adds |
|---|---|---|---|
| NO2 | hours | ~0 | most of what you see |
| CH4 | ~9 years | ~1900 ppb | ~1% |
| CO2 | centuries | ~420 ppm | ~0.01% |

NO2 is destroyed within hours of being emitted, so it never accumulates: over
clean air there is nearly none, and whatever you see near a city is that
city's. CO2 survives for centuries and mixes globally, so by the time you look
at Edmonton, the air above it is already carrying every molecule the world has
emitted for a hundred years. Edmonton's own contribution is a rounding error
on top of that.

Measured over the same box, the same month (July 2021), using this app's own
method — AOI mean minus padded-background mean:

```
gas         AOI      background   enhancement   % of bg   signal/noise
NO2      109.066        81.838       +27.229    33.271%       2.44      µmol/m²
CH4     1853.954      1840.322       +13.632     0.741%       2.81      ppb
CO2      411.328       411.314        +0.014     0.003%       0.25      ppm
```

`signal/noise` is the enhancement divided by the spread inside the AOI itself.
Under ~1 the area is not distinguishable from its own internal variation. CO2
is at 0.25. **The app's core question returns nothing for CO2.**

This is also why OCO-2 gave up swath for precision. To see 0.01% you need
per-sounding precision near 0.25 ppm, which needs far more photons per
sounding than a wide scan allows.

## 3. Why the number is a ratio, not a column

Note the units. NO2 and SO2 report mol/m2 — an absolute column. CH4 and CO2
report a **mixing ratio**: molecules of gas per molecule of dry air, in ppb
and ppm.

You cannot weigh the air directly, so OCO-2 measures a second gas to get the
denominator: **O2, which is a fixed 20.95% of dry air everywhere on Earth,
always.** The instrument reads the O2 A-band at 0.76 µm to get the air column
and two CO2 bands at 1.61 and 2.06 µm to get the CO2 column, then divides.

That is the answer to "how do we convert the raw value to ppm": **we don't.**
The division is the retrieval. `xco2` in a Lite file is already bias-corrected
ppm, and reporting it in ppb (420,000) would only make it unreadable next to
CH4's 1900.

## 4. The thing with no analogue in the other four: the biosphere

Over Alberta, 2015-2022, in order of how much they move the number:

```
long-term rise             +2.49 ppm / year
seasonal swing              8.04 ppm peak to trough   (high April, low August)
Edmonton vs its surroundings  +0.014 ppm
```

The seasonal swing is ~600x the city signal and the annual rise is ~180x.
Neither is industrial. Plants in the northern hemisphere draw CO2 down all
summer and release it as things decay through winter, so the whole hemisphere
breathes once a year. Alberta is boreal forest; it breathes hard.

Two consequences:

- **You cannot compare two dates without detrending and deseasonalising.**
  August 2021 vs April 2021 differs by 8 ppm for reasons that have nothing to
  do with emissions.
- **Alberta reads *below* its own background box in July (-0.47 ppm).** Not
  because it emits less, but because the land cover inside and outside the box
  photosynthesises at different rates. The padded-background method measures
  vegetation, not industry.

CH4 and NO2 have seasonal cycles too, but theirs are small next to their
source signals. CO2's is the opposite.

## 5. Resolution: Edmonton is smaller than one pixel

Measurements falling inside the Edmonton AOI (0.3° square) in July 2021:

```
NO2   49
CH4   30
CO2    2
```

The gridded XCO2 product's cell is 0.5° x 0.625° — larger than the whole AOI.
Edmonton's "mean" is an interpolation between two cells whose centres are
tens of kilometres outside the city.

Worse, that product (`oco2geos-co2-daygrid-v10r`) is **GEOS assimilation**: an
atmospheric transport model nudged toward OCO-2 soundings. The value over
Edmonton is the model's estimate, informed by soundings that may be hundreds
of kilometres away. Running `hotspot_regions` on it would segment the model's
smoothing and label it a detection. That is exactly the failure mode the SO2
config already refuses to commit.

Its coverage also **stops at 2022-02-28**. It cannot answer a question about
this year.

## 6. What does work: targeted snapshots

OCO-2 and OCO-3 can be pointed at a site instead of scanning past it. One such
snapshot over the Athabasca oil sands:

```
oco2-co2_mildredLakeCa_2025-09-06...   2025-09-06, ~1° box
soundings 3863    mean 421.86 ppm    spread 4.34 ppm    std 1.08
```

3863 soundings over one industrial site in one pass, against 391 for the whole
province in the gridded product, and a 4.3 ppm spread inside the box — real
structure, not interpolation. There are 571 such items over the Alberta box,
running to September 2025.

This is the only observational CO2 product in scope that shows an industrial
source at a resolution worth mapping.

## 7. Sources, and what each is for

| source | what it is | resolution | period | login |
|---|---|---|---|---|
| `oco2geos-co2-daygrid-v10r` | XCO2, model-assimilated | 0.5° x 0.625°, daily | 2015-01 .. 2022-02 | no |
| `oco3-co2-sams-daygrid-v11r` | XCO2, targeted snapshots | ~2 km | .. 2025-09 | no |
| `odiac-ffco2-monthgrid-v2024` | fossil-fuel CO2 *emissions* inventory | 1 km, monthly | 2000 .. 2023 | no |
| `OCO2_L2_Lite_FP` via earthaccess | XCO2, raw soundings | ~2 km, along-track | .. present (weeks lag) | yes |

All three GHG Center collections are served by a STAC catalogue and a
titiler raster API that does zonal statistics server-side — the same operation
as `reduceRegion`, over HTTP, no credentials. `co2/explore.py` uses only that.

## 8. A trap worth knowing

A few days in `oco2geos-co2-daygrid-v10r` are written as **all-zero rasters**
instead of masked nodata, and the statistics endpoint counts those zeros as
valid pixels. One such day (2017-06-16) was enough to drag June's seasonal
mean down by 7 ppm and invent a cycle that does not exist. Anything reading
this collection must drop days below a plausibility floor — see
`MIN_PLAUSIBLE_PPM` in `explore.py`.

## 9. What was built, and the shape it took

Five analyses behind five tabs, because there is no single CO2 number.

| tab | product | kind | works at city scale? | reaches today? |
|---|---|---|---|---|
| Trend & seasonal cycle | assimilated XCO2 | assimilation | no | no (ends 2022-02) |
| vs. surroundings | assimilated XCO2 | assimilation | no | no |
| Emissions inventory | ODIAC | inventory | **yes** | no (ends 2023-12) |
| Targeted snapshots | OCO-2/3 SAMs | observation | yes, where aimed | to 2025-09 |
| CO2 inferred from NO2 | Sentinel-5P NO2 | inference | **yes** | **yes** |

Only the last row does both, which is why it is the one that makes CO2 worth
adding to an app that already has NO2.

**Refusal is a first-class outcome.** `analysis.adequacy()` runs before any
number is computed and compares the AOI against the product's cell size.
Edmonton spans **0.3** of an XCO2 grid cell, so the trend and anomaly tabs
decline, explain, and draw the grid over the map so the reader can see the
city sitting inside one rectangle. Nothing is interpolated into a metric.

**Every number is labelled by what kind of claim it is** — measured,
assimilated, modelled, or inferred — with a badge at the top of each tab.
These are four genuinely different epistemic statuses and the page never lets
them blur.

### Numbers worth keeping as regression checks

- Alberta trend **+2.49 ppm/yr**, seasonal swing **8.04 ppm**, April high /
  August low, left-over scatter **±1.14 ppm**.
- Alaska, for contrast: **+2.46 ppm/yr**, swing **9.13 ppm** — further north,
  more boreal, a deeper breath. Same April/August phase.
- Alberta vs its surrounding box, deseasonalised: **−0.005 ppm**, noise
  **±0.366**, signal/noise **−0.01** → *Within noise*. The correct answer.
- ODIAC over Alberta, December 2023: **168.2 Mt CO2/yr**, against a real
  provincial fossil-fuel figure near 170. This is the single best check that
  the unit handling is right — see the three traps in `inventory_totals()`.
- Biggest single ODIAC cell in Alberta: **15.8 Mt CO2/yr** from one ~0.5 km²
  cell, which is the oil sands upgrader complex.
- Edmonton NO2 **+27.6 µmol/m² (+33.7%)** → implied combustion CO2
  **0.093 ppm**, range **0.039–0.232**. The assimilated product's direct
  answer for the same city and month is **+0.014 ppm** — below what it can
  resolve, which is exactly the point.

### Two unit traps that cost real debugging

1. **ODIAC is tonnes of carbon, on a 1/120° grid, with empty cells for
   non-emitting land.** Three separate corrections: ×44/12 for CO2, a real
   cell area (0.497 km² at Alberta's latitude, not 1 km²), and totals from
   `mean × count` rather than `mean × area` — `count` is *emitting* cells and
   only 23% of Alberta's qualify. Getting the last one wrong inflated the
   provincial total from 168 to 458 Mt.
2. **The all-zero nodata days in the XCO2 collection** — §8. One day made
   June's seasonal anomaly −10.7 ppm and moved the apparent minimum from
   August to June.

## 10. The NO2 band bug (found by cross-checking against the NO2 page)

The inferred tab read `NO2_column_number_density`. The NO2 page reads
`tropospheric_NO2_column_number_density`. Those are different bands and the
first one is wrong for this purpose.

The total column includes the **stratosphere**, where NO2 sits at high
concentration everywhere and has nothing to do with anything burning on the
ground. Over Athabasca, 2021-09 to 2025-09:

```
                    total column     tropospheric      (NO2 page)
AOI                     60.20            13.18
background              58.21            10.35
difference              +1.99            +2.83
as % of background       +3.4%           +27.4%
```

Roughly four fifths of the total column is stratospheric. That part is
near-uniform across the AOI and its background box, so it survives the
subtraction as dead weight in the denominator — which is why the percentage
collapsed from +27.4% to +3.4% while the absolute difference only changed by
a third.

Two smaller mismatches were fixed alongside it:

- **No `filterBounds`**, so images that never crossed the box were being
  averaged in.
- **The background box was reduced at 5500 m** instead of the 15000 m
  `no2/config.py` uses for a context box.

Effect on the answer: implied combustion CO2 over Athabasca went from
0.003 / 0.007 / 0.017 ppm to **0.004 / 0.0095 / 0.024 ppm** — about 40%
higher.

**The lesson worth keeping:** the inferred tab rests entirely on numbers the
NO2 page already computes, so the two pages agreeing is a free correctness
check, and it is the only one available for an inference whose output nothing
can measure directly. Re-run it after touching `no2_stats`:

```
Athabasca, 2021-09-01..2025-09-30  ->  13.18 / 10.35 / +2.83 / +27.4%
```
