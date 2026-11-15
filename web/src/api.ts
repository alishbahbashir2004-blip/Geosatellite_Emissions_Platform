// Central API client. Errors surface the server's `detail` field when present,
// otherwise a generic network message.

import type {
  Co2Config, Co2Result, DashboardCard, GasDescriptor, GasRun, Location,
  MapDescriptor, Query, VegaSpec,
} from './types'

async function handle<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const body = await response.json()
      if (body?.detail) detail = body.detail
    } catch { /* a non-JSON error body: keep the status line */ }
    throw new Error(detail)
  }
  return response.json() as Promise<T>
}

async function get<T>(path: string): Promise<T> {
  return handle<T>(await fetch(path))
}

async function post<T>(path: string, body: unknown): Promise<T> {
  return handle<T>(await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }))
}

export const api = {
  dashboard: () => get<{ gases: DashboardCard[] }>('/api/dashboard'),

  places: () => get<{ regions: Record<string, any>; cities: string[] }>(
    '/api/places'),

  resolve: (location: Location) =>
    post<{ bbox: any; label: string; map: MapDescriptor }>(
      '/api/resolve', location),

  gas: (key: string) => get<GasDescriptor>(`/api/gas/${key}`),

  runGas: (key: string, query: Query) =>
    post<GasRun>(`/api/gas/${key}/run`, query),

  compareGas: (key: string, areas: Query[], selected: number) =>
    post<any>(`/api/gas/${key}/compare`, { areas, selected }),

  co2Config: () => get<Co2Config>('/api/co2'),

  co2Coverage: (query: Query) =>
    post<{ rows: any[]; chart: VegaSpec }>('/api/co2/coverage', query),

  co2: (analysis: string, query: Query) =>
    post<Co2Result>(`/api/co2/${analysis}`, query),
}
