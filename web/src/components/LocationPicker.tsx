// Location and date controls shared by every page: a named region, a city,
// or raw coordinates.

import type { Query } from '../types'

export type Mode = 'region' | 'city' | 'coords'

export interface Selection {
  mode: Mode
  region: string
  city: string
  N: number; S: number; W: number; E: number
  start: string; end: string
}

export const DEFAULT_SELECTION: Selection = {
  mode: 'region', region: 'Athabasca', city: 'Edmonton',
  N: 60, S: 49, W: -120, E: -110,
  start: '2021-07-01', end: '2021-07-31',
}

/** A Selection as the body the API expects. */
export function toQuery(selection: Selection): Query {
  const dates = { date_start: selection.start, date_end: selection.end }
  if (selection.mode === 'region') return { region_name: selection.region, ...dates }
  if (selection.mode === 'city') return { city_name: selection.city, ...dates }
  return {
    N: selection.N, S: selection.S, W: selection.W, E: selection.E, ...dates,
  }
}

export function labelOf(selection: Selection): string {
  if (selection.mode === 'region') return selection.region
  if (selection.mode === 'city') return selection.city
  return 'Selected area'
}

export function LocationPicker({ value, onChange, regions, cities, note }: {
  value: Selection
  onChange: (next: Selection) => void
  regions: string[]
  cities: string[]
  note?: string
}) {
  const set = (patch: Partial<Selection>) => onChange({ ...value, ...patch })

  return (
    <div>
      <div className="radio-row">
        {([['region', 'Region name'], ['city', 'City name'],
           ['coords', 'Coordinates']] as [Mode, string][]).map(([mode, text]) => (
          <label key={mode}>
            <input type="radio" checked={value.mode === mode}
                   onChange={() => set({ mode })} />
            {text}
          </label>
        ))}
      </div>

      {value.mode === 'region' && (
        <>
          <label className="field">Region</label>
          <select value={value.region} onChange={(e) => set({ region: e.target.value })}>
            {regions.map((name) => <option key={name}>{name}</option>)}
          </select>
        </>
      )}

      {value.mode === 'city' && (
        <>
          <label className="field">City</label>
          <select value={value.city} onChange={(e) => set({ city: e.target.value })}>
            {cities.map((name) => <option key={name}>{name}</option>)}
          </select>
        </>
      )}

      {value.mode === 'coords' && (
        <div className="row">
          <div className="col">
            <label className="field">North</label>
            <input type="number" value={value.N}
                   onChange={(e) => set({ N: Number(e.target.value) })} />
            <label className="field" style={{ marginTop: '.5rem' }}>South</label>
            <input type="number" value={value.S}
                   onChange={(e) => set({ S: Number(e.target.value) })} />
          </div>
          <div className="col">
            <label className="field">West</label>
            <input type="number" value={value.W}
                   onChange={(e) => set({ W: Number(e.target.value) })} />
            <label className="field" style={{ marginTop: '.5rem' }}>East</label>
            <input type="number" value={value.E}
                   onChange={(e) => set({ E: Number(e.target.value) })} />
          </div>
        </div>
      )}

      <div className="row" style={{ marginTop: '.7rem' }}>
        <div className="col">
          <label className="field">Start date</label>
          <input type="date" value={value.start}
                 onChange={(e) => set({ start: e.target.value })} />
        </div>
        <div className="col">
          <label className="field">End date</label>
          <input type="date" value={value.end}
                 onChange={(e) => set({ end: e.target.value })} />
        </div>
      </div>

      {note && <div className="caption" style={{ marginTop: '.4rem' }}>{note}</div>}
    </div>
  )
}
