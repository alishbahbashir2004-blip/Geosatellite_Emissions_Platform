// Shared page for the four Sentinel-5P gases. One component since all four
// return the same state shape
// CO2 has its own page (Co2Page.tsx) since it has no single result shape.

import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { useApi } from '../useApi'
import { ResultMap } from '../components/ResultMap'
import { VegaChart } from '../components/VegaChart'
import {
  Callout, Caption, Html, LevelDelta, LevelKey, Metric, Metrics, Tabs, Working,
  fmt,
} from '../components/ui'
import {
  DEFAULT_SELECTION, LocationPicker, labelOf, toQuery,
  type Selection,
} from '../components/LocationPicker'
import type { GasDescriptor, GasRun, MapDescriptor } from '../types'

export function GasPage({ gasKey }: { gasKey: string }) {
  const { data: gas, error: gasError } = useApi(
    () => api.gas(gasKey), [gasKey])
  const { data: places } = useApi(() => api.places(), [])

  const [selection, setSelection] = useState<Selection>(DEFAULT_SELECTION)
  const [view, setView] = useState<'single' | 'compare'>('single')

  // Reset to single-area view on gas change, so a compare view left open
  // doesn't carry over to the next gas.
  useEffect(() => { setView('single') }, [gasKey])

  if (gasError) return <div className="error">{gasError}</div>
  if (!gas || !places) return <Working what="Loading…" />

  const regions = Object.keys(places.regions).sort()

  return (
    <>
      <div className="page-head">
        <h1>{gas.name} Agent</h1>
        <p>{gas.product} ({gas.unit}), measured against the surrounding region</p>
      </div>

      {gas.hasCompare && (
        <Tabs
          tabs={[{ id: 'single', label: 'One area' },
                 { id: 'compare', label: 'Compare two areas' }]}
          active={view}
          onChange={(id) => setView(id as 'single' | 'compare')}
        />
      )}

      {view === 'single'
        ? <SingleArea gas={gas} regions={regions} cities={places.cities}
                      selection={selection} setSelection={setSelection} />
        : <CompareAreas gas={gas} regions={regions} cities={places.cities} />}
    </>
  )
}

// ---------------------------------------------------------------------------
// One area against the padded box around it
// ---------------------------------------------------------------------------

function SingleArea({ gas, regions, cities, selection, setSelection }: {
  gas: GasDescriptor; regions: string[]; cities: string[]
  selection: Selection; setSelection: (next: Selection) => void
}) {
  const [run, setRun] = useState<GasRun | null>(null)
  const [preview, setPreview] = useState<MapDescriptor | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [shown, setShown] = useState(gas.defaultHotspots)

  // Preview the resolved box before a query is run.
  useEffect(() => {
    let cancelled = false
    api.resolve(toQuery(selection))
      .then((r) => { if (!cancelled) setPreview(r.map) })
      .catch(() => { if (!cancelled) setPreview(null) })
    return () => { cancelled = true }
  }, [selection.mode, selection.region, selection.city,
      selection.N, selection.S, selection.W, selection.E])

  const label = labelOf(selection)

  async function go() {
    setBusy(true); setFailure(null)
    try {
      const answer = await api.runGas(gas.key, toQuery(selection))
      setRun(answer)
      setShown(Math.min(gas.defaultHotspots,
                        answer.map?.hotspotBoxes?.length ?? 0) || gas.defaultHotspots)
    } catch (e) {
      setFailure((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const result = run?.result
  const value = (key: string) => result?.[key]
  const unit = gas.unit

  const available = run?.map?.hotspotBoxes?.length ?? 0
  // What the backend actually found, which can exceed what it returned.
  const found = result?.hotspot_region_count ?? available

  return (
    <>
      <div className="panel">
        <div className="row">
          <div className="col">
            <h3>Location &amp; date range</h3>
            <LocationPicker value={selection} onChange={setSelection}
                            regions={regions} cities={cities}
                            note={`${gas.formula} coverage starts ${gas.coverageStart}.`} />
            <div style={{ marginTop: '.9rem' }}>
              <button className="primary" onClick={go} disabled={busy}>
                {busy ? 'Querying Earth Engine…' : `Get ${gas.formula} column`}
              </button>
            </div>
            {busy && <Working what="Reducing the area and its surroundings…" />}
            {failure && <div className="error">{failure}</div>}
            {run?.error && <Callout tone="stop">{run.error}</Callout>}
          </div>

          <div className="col" style={{ minWidth: 380 }}>
            <h3>Map</h3>
            {run?.map
              ? <ResultMap descriptor={run.map} maxHotspots={shown} />
              : preview
                ? <ResultMap descriptor={preview} />
                : <div className="map" />}
            {available > 1 && (
              <div style={{ marginTop: '.6rem' }}>
                <label className="field">
                  Hotspot boxes to draw — {shown} of {available}
                </label>
                <input type="range" min={1} max={available} value={shown}
                       style={{ width: '100%' }}
                       onChange={(e) => setShown(Number(e.target.value))} />
                <Caption>
                  Ranked by patch mean, hottest first. The rest are weaker and
                  clutter the raster.
                </Caption>
              </div>
            )}
            {run?.result?.hotspot_error && (
              <Callout tone="warn">{run.result.hotspot_error}</Callout>
            )}
          </div>
        </div>
      </div>

      {result && (
        <>
          <div className="panel">
            <Caption>{label} — {value('pass_count')} satellite passes</Caption>
            <Metrics>
              <Metric label={`Mean ${gas.formula} (${unit})`}
                      value={fmt(value(`mean_${gas.statSuffix}`), gas.digits)} />
              <Metric label={`Background (${unit})`}
                      value={fmt(value(`background_${gas.statSuffix}`), gas.digits)} />
              <Metric
                label="Above background"
                value={gas.headlinePct
                  ? `${fmt(value('enhancement_pct'), 1, true)}%`
                  : `${fmt(value(gas.enhancementKey), gas.digits, true)} ${unit}`}
                delta={<LevelDelta level={value('level')}
                                   value={gas.headlinePct
                                     ? value('enhancement_pct')
                                     : value(gas.enhancementKey)} />}
                help={gas.headlinePct
                  ? 'Percent of the local background column — the level bands are assigned on this.'
                  : 'Absolute difference from the local background.'}
              />
            </Metrics>

            {gas.noiseNote && <Callout tone="warn" html={gas.noiseNote} />}

            <Metrics>
              <Metric label={`Min (${unit})`}
                      value={fmt(value(`min_${gas.statSuffix}`), gas.digits)} />
              <Metric label={`Median (${unit})`}
                      value={fmt(value(`median_${gas.statSuffix}`), gas.digits)} />
              <Metric label={`Max (${unit})`}
                      value={fmt(value(`max_${gas.statSuffix}`), gas.digits)} />
            </Metrics>

            <Metrics>
              <Metric label={`P10–P80 (${unit})`}
                      value={`${fmt(value(`p10_${gas.statSuffix}`), gas.digits)}–${fmt(value(`p80_${gas.statSuffix}`), gas.digits)}`}
                      help="The middle 70% of the area's pixels." />
              <Metric label={`P10–P80 mean (${unit})`}
                      value={fmt(value(`core_mean_${gas.statSuffix}`), gas.digits)}
                      help="Mean of the pixels inside P10–P80, so both tails are excluded." />
              <Metric label="P10–P80 above bg"
                      value={gas.headlinePct
                        ? `${fmt(value('core_enhancement_pct'), 1, true)}%`
                        : `${fmt(value(`core_${gas.enhancementKey}`), gas.digits, true)} ${unit}`}
                      delta={<LevelDelta level={value('core_level')}
                                         value={gas.headlinePct
                                           ? value('core_enhancement_pct')
                                           : value(`core_${gas.enhancementKey}`)} />} />
            </Metrics>

            <Metrics>
              <Metric label="Hotspot above bg"
                      value={gas.headlinePct
                        ? `${fmt(value('hotspot_enhancement_pct'), 1, true)}%`
                        : `${fmt(value(`hotspot_${gas.enhancementKey}`), gas.digits, true)} ${unit}`}
                      delta={<LevelDelta level={value('hotspot_level')}
                                         value={gas.headlinePct
                                           ? value('hotspot_enhancement_pct')
                                           : value(`hotspot_${gas.enhancementKey}`)} />}
                      help="Hottest fifth of the pixels (P80) against local background." />
              <Metric label="Peak above bg"
                      value={gas.headlinePct
                        ? `${fmt(value('peak_enhancement_pct'), 1, true)}%`
                        : `${fmt(value(`peak_${gas.enhancementKey}`), gas.digits, true)} ${unit}`}
                      help="Highest single pixel against local background." />
              <Metric label="Hotspot regions boxed"
                      value={found > available
                        ? `${available} of ${found}`
                        : `${available}`}
                      help={`${found} contiguous patch(es) of above-P80 pixels were found inside the area; the ${shown} with the highest mean are drawn on the map, numbered hottest first.`} />
            </Metrics>

            {run?.levelLegend && (
              <div style={{ marginTop: '.8rem' }}>
                <Html html={run.levelLegend} />
              </div>
            )}
          </div>

          <ChartGrid charts={run.charts} />
        </>
      )}

      {!result && (
        <LevelKey levels={gas.levels} unit={gas.levelUnit}
                  title={gas.levelTitle} digits={gas.digits} />
      )}
    </>
  )
}

function ChartGrid({ charts }: { charts?: Record<string, any> }) {
  if (!charts) return null
  const figures: [string, string][] = [
    ['series', 'Daily mean over the period'],
    ['availability', 'Pixel availability'],
    ['box', 'Spread across the area'],
    ['histogram', 'Distribution — selected area'],
    ['backgroundHistogram', 'Distribution — surrounding region'],
  ]
  return (
    <>
      {figures.filter(([id]) => charts[id]).map(([id, title]) => (
        <div className="panel" key={id}>
          <h4>{title}</h4>
          <VegaChart spec={charts[id]} />
        </div>
      ))}
    </>
  )
}

// ---------------------------------------------------------------------------
// Two areas read against each other
// ---------------------------------------------------------------------------

function CompareAreas({ gas, regions, cities }: {
  gas: GasDescriptor; regions: string[]; cities: string[]
}) {
  const [left, setLeft] = useState<Selection>(DEFAULT_SELECTION)
  const [right, setRight] = useState<Selection>(
    { ...DEFAULT_SELECTION, region: 'Montney' })
  const [answer, setAnswer] = useState<any>(null)
  const [selected, setSelected] = useState(0)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  const labels = useMemo(() => [labelOf(left), labelOf(right)], [left, right])

  async function go(which = selected) {
    setBusy(true); setFailure(null)
    try {
      setAnswer(await api.compareGas(
        gas.key, [toQuery(left), toQuery(right)], which))
    } catch (e) {
      setFailure((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="panel">
        <div className="row">
          <div className="col">
            <h3>First area</h3>
            <LocationPicker value={left} onChange={setLeft}
                            regions={regions} cities={cities} />
          </div>
          <div className="col">
            <h3>Second area</h3>
            <LocationPicker value={right} onChange={setRight}
                            regions={regions} cities={cities} />
          </div>
        </div>
        <div style={{ marginTop: '.9rem' }}>
          <button className="primary" onClick={() => go()} disabled={busy}>
            {busy ? 'Querying…' : 'Compare'}
          </button>
        </div>
        {busy && <Working what="Measuring both areas over the same dates…" />}
        {failure && <div className="error">{failure}</div>}
        {answer?.error && <Callout tone="stop">{answer.error}</Callout>}
      </div>

      {answer && !answer.error && (
        <>
          <div className="panel">
            <div className="radio-row">
              {labels.map((name, i) => (
                <label key={name}>
                  <input type="radio" checked={selected === i}
                         onChange={() => { setSelected(i); go(i) }} />
                  Show {name}'s raster
                </label>
              ))}
            </div>
            <ResultMap descriptor={answer.map} />
            <Caption>
              Only one raster is drawn at a time — two would overlap into an
              unreadable stack wherever the areas are close, and the colour bar
              can only describe one stretch honestly. Both areas' outlines and
              patches stay on the map either way.
            </Caption>
          </div>

          <div className="row">
            {answer.areas.map((area: any) => (
              <div className="col panel" key={area.label}>
                <h3>{area.label}</h3>
                <Metrics>
                  <Metric label={`Mean (${gas.unit})`}
                          value={fmt(area.result[`mean_${gas.statSuffix}`], gas.digits)} />
                  <Metric label="Above background"
                          value={gas.headlinePct
                            ? `${fmt(area.result.enhancement_pct, 1, true)}%`
                            : `${fmt(area.result[gas.enhancementKey], gas.digits, true)} ${gas.unit}`}
                          delta={<LevelDelta level={area.result.level}
                                             value={gas.headlinePct
                                               ? area.result.enhancement_pct
                                               : area.result[gas.enhancementKey]} />} />
                </Metrics>
                <VegaChart spec={area.charts.series} />
              </div>
            ))}
          </div>
        </>
      )}
    </>
  )
}
