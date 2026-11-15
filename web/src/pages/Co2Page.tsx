// The CO2 page: five tabs, each a different product and a different kind of
// claim (measured / modelled / assimilated / inferred
// each free to decline if data not available in asked time range and say why 

import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApi, useRunner } from '../useApi'
import { ResultMap } from '../components/ResultMap'
import { VegaChart } from '../components/VegaChart'
import {
  Callout, Caption, LevelKey, Metric, Metrics, Tabs, Working, fmt,
} from '../components/ui'
import {
  DEFAULT_SELECTION, LocationPicker, toQuery, type Selection,
} from '../components/LocationPicker'
import type { Co2Config, Co2Result } from '../types'

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
                'August', 'September', 'October', 'November', 'December']

const KIND_BADGE: Record<string, [string, string, string]> = {
  observation: ['#2e7d32', 'MEASURED', 'Real soundings. A satellite saw this.'],
  assimilation: ['#f57c00', 'ASSIMILATED',
    'A transport model, pulled towards real soundings every six hours. ' +
    'Gap-free because the model fills the gaps.'],
  inventory: ['#6a1b9a', 'MODELLED',
    'A bottom-up emissions estimate spread over a grid. Nothing here was ' +
    'measured in the atmosphere.'],
  inferred: ['#0277bd', 'INFERRED',
    'Calculated from a different gas that was measured. No satellite saw ' +
    'this CO2.'],
}

function Badge({ kind }: { kind: string }) {
  const [color, text, note] = KIND_BADGE[kind]
  return (
    <div className="badge-row">
      <span className="badge" style={{ background: color }}>{text}</span>
      <span className="note">{note}</span>
    </div>
  )
}

/** The standard "no reading, and here is why" block, used by every tab. */
function Unavailable({ result, extra }: { result: Co2Result; extra?: string }) {
  return (
    <>
      <h4>{result.reason}</h4>
      <Callout tone="stop" html={result.detail} />
      {extra && <Callout html={extra} />}
      {result.adequacy && (
        <Metrics>
          <Metric label="Your area spans"
                  value={`${result.adequacy.cells.toFixed(1)} cells`} />
          <Metric label="One cell is"
                  value={`${result.adequacy.cell_km[0].toFixed(0)} × ${result.adequacy.cell_km[1].toFixed(0)} km`} />
          <Metric label="Needed for a reading" value="4 cells (2×2)" />
        </Metrics>
      )}
      {result.map && <ResultMap descriptor={result.map} />}
      {result.map && (
        <Caption>
          Each white rectangle is one grid cell of the product. The blue box is
          your area.
        </Caption>
      )}
    </>
  )
}

export function Co2Page() {
  const { data: config, error } = useApi(() => api.co2Config(), [])
  const { data: places } = useApi(() => api.places(), [])
  const [selection, setSelection] = useState<Selection>(
    { ...DEFAULT_SELECTION, region: 'Athabasca',
      start: '2021-09-01', end: '2025-09-30' })
  const [tab, setTab] = useState('trend')
  const coverage = useRunner<{ rows: any[]; chart: any }>()

  useEffect(() => {
    coverage.run(() => api.co2Coverage(toQuery(selection)))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selection.start, selection.end])

  if (error) return <div className="error">{error}</div>
  if (!config || !places) return <Working what="Loading…" />

  const regions = Object.keys(places.regions).sort()
  const stale = (coverage.data?.rows ?? []).filter((r) => !r.covers_request)

  const tabs = [
    { id: 'trend', label: 'Trend & seasonal cycle' },
    { id: 'anomaly', label: 'vs. surroundings' },
    { id: 'inventory', label: 'Emissions inventory' },
    { id: 'snapshots', label: 'Targeted snapshots' },
    { id: 'inferred', label: 'CO2 inferred from NO2' },
  ]

  return (
    <>
      <div className="page-head">
        <h1>Carbon Dioxide Agent</h1>
        <p>
          CO2 is not measured the way the other four gases are, and cannot be
          read the same way. Four products, four different kinds of claim, and
          one inference from NO2.
        </p>
      </div>

      <div className="panel">
        <div className="row">
          <div className="col">
            <LocationPicker value={selection} onChange={setSelection}
                            regions={regions} cities={places.cities} />
          </div>
          <div className="col" style={{ minWidth: 420 }}>
            <h4>What CO2 data exists, and when</h4>
            {coverage.busy && <Working what="Checking coverage…" />}
            <VegaChart spec={coverage.data?.chart ?? null} />
          </div>
        </div>
      </div>

      {stale.length > 0 && (
        <Callout tone="warn">
          <b>Your date range falls outside {stale.length} of the five sources:</b>{' '}
          {stale.map((r) => r.label).join(', ')}. Those tabs will use their
          nearest data instead, or decline and say why.
        </Callout>
      )}

      <Tabs tabs={tabs} active={tab} onChange={setTab} />

      {tab === 'trend' && <TrendTab config={config} selection={selection} />}
      {tab === 'anomaly' && <AnomalyTab config={config} selection={selection} />}
      {tab === 'inventory' && <InventoryTab config={config} selection={selection} />}
      {tab === 'snapshots' && <SnapshotTab config={config} selection={selection} />}
      {tab === 'inferred' && <InferredTab config={config} selection={selection} />}
    </>
  )
}

interface TabProps { config: Co2Config; selection: Selection }

/** Everything a tab shares: the run button, the spinner and the error line. */
function RunPanel({ label, busy, error, onRun }: {
  label: string; busy: boolean; error: string | null; onRun: () => void
}) {
  return (
    <>
      <button className="primary" onClick={onRun} disabled={busy}>
        {busy ? 'Working…' : label}
      </button>
      {busy && <Working what="Reading from NASA's GHG Center…" />}
      {error && <div className="error">{error}</div>}
    </>
  )
}

// ---------------------------------------------------------------------------

function TrendTab({ config, selection }: TabProps) {
  const runner = useRunner<Co2Result>()
  const source = config.sources.xco2_grid
  const r = runner.data

  return (
    <>
      <Badge kind={source.kind} />
      <Caption><span dangerouslySetInnerHTML={{ __html: source.whatItIs }} /></Caption>
      <Callout>
        Reads the <b>entire record</b> for your area, not your selected dates —
        a trend needs years of data. Your window is shaded on the chart.
      </Callout>
      <RunPanel label="Read the CO2 record for this area" busy={runner.busy}
                error={runner.error}
                onRun={() => runner.run(() => api.co2('trend', toQuery(selection)))} />

      {r && !r.available && (
        <Unavailable result={r}
                     extra={r.reason?.includes('smaller') ? config.prose.tooSmall : undefined} />
      )}

      {r?.available && (
        <>
          <Metrics>
            <Metric label="Long-term rise"
                    value={`${fmt(r.slope_ppm_per_year, 2, true)} ppm/yr`} />
            <Metric label="Seasonal swing"
                    value={`${fmt(r.seasonal_amplitude, 2)} ppm`}
                    help="Peak-to-trough of the yearly cycle, averaged over every full year in the record." />
            <Metric label="High / low month"
                    value={r.seasonal_max_month
                      ? `${MONTHS[r.seasonal_max_month - 1].slice(0, 3)} / ${MONTHS[r.seasonal_min_month - 1].slice(0, 3)}`
                      : '—'} />
            <Metric label="Left-over scatter"
                    value={`±${fmt(r.remainder_std, 2)} ppm`}
                    help="Standard deviation of what remains once the rise and the yearly cycle are removed. Anything smaller cannot be distinguished from noise." />
          </Metrics>
          <Caption>
            {r.n} usable days between {r.first} and {r.last}; the area spans{' '}
            {r.adequacy?.cells.toFixed(0)} grid cells.
          </Caption>

          <VegaChart spec={r.charts?.record ?? null} />
          <Callout html={config.prose.trend} />

          {r.charts?.seasonal && (
            <>
              <h4>The yearly cycle, on its own</h4>
              <VegaChart spec={r.charts.seasonal} />
              <Callout html={r.prose?.seasonal ?? config.prose.seasonal} />
            </>
          )}

          <h4>What is left once both are removed</h4>
          <VegaChart spec={r.charts?.remainder ?? null} />
          <Callout html={r.prose?.deseasonalise ?? config.prose.deseasonalise} />
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------

function AnomalyTab({ config, selection }: TabProps) {
  const runner = useRunner<Co2Result>()
  const r = runner.data

  return (
    <>
      <Badge kind="assimilation" />
      <Callout>
        The same question the other gas pages ask — is this area above its
        surroundings? — but with trend and season removed from both boxes first.
      </Callout>
      <Callout>
        <b>Ignores the dates you picked above</b> — removing a trend and season
        needs the product's whole record (2015-01-01 to 2022-02-28, weekly).
      </Callout>
      <Callout tone="warn" html={config.prose.noEnhancement} />
      <RunPanel label="Compare this area with its surroundings" busy={runner.busy}
                error={runner.error}
                onRun={() => runner.run(() => api.co2('anomaly', toQuery(selection)))} />

      {r && !r.available && (
        <Unavailable result={r}
                     extra={r.reason?.includes('smaller') ? config.prose.tooSmall : undefined} />
      )}

      {r?.available && (
        <>
          <Metrics>
            <Metric label="Area vs surroundings"
                    value={`${fmt(r.mean_anomaly, 3, true)} ppm`} />
            <Metric label="Scatter of that difference"
                    value={`±${fmt(r.anomaly_noise, 3)} ppm`}
                    help="How much that difference moves from day to day. A difference smaller than this cannot be told apart from the product's own jitter." />
          </Metrics>
          <div style={{ fontSize: '1.05rem', margin: '.3rem 0' }}>
            <b style={{ color: r.level_color }}>{r.level}</b>
          </div>
          <LevelKey levels={config.levels} unit={config.levelUnit}
                    title={config.levelTitle} digits={1} />
          <Caption>{r.n} days where both boxes had a usable value.</Caption>

          <VegaChart spec={r.charts?.anomaly ?? null} />
          <Callout tone="warn" html={config.prose.landCover} />

          <h4>The two boxes, and the grid they are measured on</h4>
          {r.map && <ResultMap descriptor={r.map} />}
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------

function InventoryTab({ config, selection }: TabProps) {
  const runner = useRunner<Co2Result>()
  const source = config.sources.odiac
  const r = runner.data
  const latest = r?.latest

  return (
    <>
      <Badge kind={source.kind} />
      <Caption><span dangerouslySetInnerHTML={{ __html: source.whatItIs }} /></Caption>
      <Callout>
        The only CO2 product here fine enough to separate a city from the
        countryside (1 km, monthly) — a modelled estimate of where CO2 is
        emitted, not a measurement of it.
      </Callout>
      <RunPanel label="Read the emissions inventory" busy={runner.busy}
                error={runner.error}
                onRun={() => runner.run(() => api.co2('inventory', toQuery(selection)))} />

      {r && !r.available && <Unavailable result={r} />}

      {r?.available && latest && (
        <>
          {r.gap && (
            <Callout tone="warn">
              Your window was trimmed to what the inventory has:{' '}
              <b>{r.window[0]} to {r.window[1]}</b>. ODIAC covers{' '}
              {r.gap.source_range[0]} to {r.gap.source_range[1]}.
            </Callout>
          )}
          <Metrics>
            <Metric label={`Emissions, ${latest.date.slice(0, 7)} × 12`}
                    value={`${latest.total_mtco2_per_year.toFixed(1)} Mt CO2/yr`}
                    help="Every emitting cell for this one month, multiplied by twelve — not a calendar-year total. December 2023 over the whole of Alberta gives 168 Mt CO2/yr this way, against a real provincial figure near 170." />
            <Metric label="Biggest single cell"
                    value={`${latest.peak_mtco2_per_year_cell.toFixed(2)} Mt CO2/yr`}
                    help="The most intense 1 km cell, annualised — a power station, refinery or upgrader complex." />
            <Metric label="Intensity"
                    value={`${Math.round(latest.mean_tco2_per_km2_month).toLocaleString()} t/km²/mo`}
                    help="Tonnes of CO2 per km² per month, over emitting land only." />
            <Metric label="Emitting land"
                    value={`${Math.round(latest.emitting_share * 100)}%`}
                    help="Share of the area with any fossil-fuel activity. ODIAC leaves the rest empty rather than zero." />
          </Metrics>
          <Caption>
            Latest month shown: {latest.date.slice(0, 7)}. Area ≈{' '}
            {Math.round(latest.area_km2).toLocaleString()} km², of which{' '}
            {Math.round(latest.emitting_km2).toLocaleString()} km² emits anything.
          </Caption>

          <details className="raw">
            <summary>Show the raw numbers and the arithmetic</summary>
            <Metrics>
              <Metric label="mean per cell"
                      value={`${latest.raw_mean_tc_per_cell.toFixed(4)} tC`} />
              <Metric label="cells with a value"
                      value={latest.raw_cell_count.toLocaleString()} />
              <Metric label="max cell"
                      value={`${latest.raw_max_tc_per_cell.toLocaleString()} tC`} />
              <Metric label="of cells in box"
                      value={`${latest.raw_valid_percent.toFixed(2)}%`} />
            </Metrics>
            <pre className="code">{`carbon -> CO2 = 44/12 = 3.6667

1  emissions  = mean x cells x 44/12 x 12 / 1e6
              = ${latest.raw_mean_tc_per_cell.toFixed(4)} x ${latest.raw_cell_count.toLocaleString()} x 3.6667 x 12 / 1e6
              = ${latest.total_mtco2_per_year.toFixed(2)} Mt CO2/yr

2  biggest    = max x 44/12 x 12 / 1e6
              = ${latest.raw_max_tc_per_cell.toLocaleString()} x 3.6667 x 12 / 1e6
              = ${latest.peak_mtco2_per_year_cell.toFixed(2)} Mt CO2/yr

3  intensity  = mean x 44/12 / cell_km2
              = ${latest.raw_mean_tc_per_cell.toFixed(4)} x 3.6667 / ${latest.cell_km2.toFixed(4)}
              = ${Math.round(latest.mean_tco2_per_km2_month).toLocaleString()} t CO2/km²/month

4  emitting   = cells x cell_km2 / box area
              = ${latest.raw_cell_count.toLocaleString()} x ${latest.cell_km2.toFixed(4)} / ${Math.round(latest.area_km2).toLocaleString()}
              = ${Math.round(latest.emitting_share * 100)}%  (${Math.round(latest.emitting_km2).toLocaleString()} km²)`}</pre>
            <Caption>
              ODIAC leaves land with no fossil-fuel activity empty rather than
              zero, so "mean per cell" is a mean over emitting cells only —
              which is why line 1 multiplies by the cell count and not by the
              box area.
            </Caption>
          </details>

          <VegaChart spec={r.charts?.monthly ?? null} />
          {r.map && <ResultMap descriptor={r.map} />}
          <Callout>
            An allocation of a national total by night-lights and plant
            locations — where emissions should be, not a plume anyone
            photographed.
          </Callout>
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------

function SnapshotTab({ config, selection }: TabProps) {
  const runner = useRunner<Co2Result>()
  const source = config.sources.sam
  const r = runner.data

  return (
    <>
      <Badge kind={source.kind} />
      <Caption><span dangerouslySetInnerHTML={{ __html: source.whatItIs }} /></Caption>
      <RunPanel label="Find targeted snapshots over this area" busy={runner.busy}
                error={runner.error}
                onRun={() => runner.run(() => api.co2('snapshots', toQuery(selection)))} />

      {r && !r.available && <Unavailable result={r} />}

      {r?.available && (
        <>
          {r.used_out_of_window && (
            <Callout tone="warn">
              No snapshot was taken over this area inside your dates
              ({r.requested[0]} to {r.requested[1]}), so the most recent one
              ever taken is shown instead: <b>{r.chosen.date}</b>. These
              overpasses are opportunistic — the satellite is aimed at a target
              list, not run on a schedule.
            </Callout>
          )}
          <Metrics>
            <Metric label="Area actually measured"
                    value={`${Math.round(r.covered_km2).toLocaleString()} km²`}
                    help={`These snapshots are published on an 800 × 800 grid across the footprint — about 80 × 140 m per cell — which is finer than the satellite's real ~2 km footprint, so one reading paints several cells. ${r.filled_cells.toLocaleString()} cells carry data out of a ${Math.round(r.footprint_km2).toLocaleString()} km² footprint. Cloud and aerosol screening account for most of the rest.`} />
            <Metric label="Mean XCO2" value={`${r.stats.mean.toFixed(2)} ppm`} />
            <Metric label="Spread across the site"
                    value={`${r.spread.toFixed(2)} ppm`} />
            <Metric label="Snapshots ever here" value={`${r.all_items.length}`} />
          </Metrics>
          <Caption>
            Showing {r.chosen.date}. {r.in_window.length} of {r.all_items.length}{' '}
            fall inside your dates.
          </Caption>

          {r.map && <ResultMap descriptor={r.map} />}
          <Callout>
            Orange = what the satellite covered this pass; blue = your
            selection. The {r.spread.toFixed(2)} ppm spread inside it is real
            structure at ~2 km, far more than the assimilated product shows.
          </Callout>

          {r.charts?.histogram && (
            <>
              <h4>Distribution of this snapshot's grid cells</h4>
              <VegaChart spec={r.charts.histogram} />
            </>
          )}
          {r.charts?.timeline && (
            <>
              <h4>Every snapshot ever taken over this area</h4>
              <VegaChart spec={r.charts.timeline} />
              <Caption>
                Each tick is one pointed overpass. The gaps are the point: this
                is not a time series.
              </Caption>
            </>
          )}
        </>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------

function InferredTab({ config, selection }: TabProps) {
  const runner = useRunner<Co2Result>()
  const r = runner.data

  return (
    <>
      <Badge kind="inferred" />
      <Callout>
        The only analysis here that works at <b>city scale</b> and{' '}
        <b>current dates</b>: combustion emits CO2 and NOx together, so the
        visible NO2 is scaled by their emission ratio.
      </Callout>
      <RunPanel label="Infer combustion CO2 from NO2" busy={runner.busy}
                error={runner.error}
                onRun={() => runner.run(() => api.co2('inferred', toQuery(selection)))} />

      {r && !r.available && <Unavailable result={r} />}

      {r?.available && (
        <>
          {r.clamped && (
            <Callout tone="warn">
              Start date moved to {r.window[0]} — Sentinel-5P NO2 begins{' '}
              {config.no2CoverageStart}.
            </Callout>
          )}

          {r.no_plume ? (
            <>
              <h4>No combustion plume to infer from</h4>
              <Callout tone="stop">
                This area's NO2 is <b>{fmt(r.no2_delta, 1, true)} µmol/m²</b>{' '}
                against its surroundings — at or below background, so there's
                no combustion signal to scale. Expected for rural areas and
                regions whose surroundings are just as industrial.
              </Callout>
            </>
          ) : (
            <>
              <Metrics>
                <Metric label="NO2 above surroundings"
                        value={`${fmt(r.no2_delta, 1, true)} µmol/m²`}
                        delta={`${fmt(r.no2_pct, 1, true)}% of background`} />
                <Metric label="Implied combustion CO2"
                        value={`${r.inferred.central.toFixed(3)} ppm`}
                        help={`Using the central CO2:NOx ratio of ${config.emissionRatios.central}:1.`} />
                <Metric label="Plausible range"
                        value={`${r.inferred.low.toFixed(3)} – ${r.inferred.high.toFixed(3)} ppm`} />
              </Metrics>

              <VegaChart spec={r.charts?.range ?? null} />
              <Callout tone="warn" html={config.prose.inferred} />

              <h4>The two boxes this came from</h4>
              {r.map && <ResultMap descriptor={r.map} />}
              <Caption>
                NO2 measured over {r.window[0]} to {r.window[1]} from{' '}
                {(r.no2_pixels ?? 0).toLocaleString()} pixels.
              </Caption>
            </>
          )}
        </>
      )}
    </>
  )
}
