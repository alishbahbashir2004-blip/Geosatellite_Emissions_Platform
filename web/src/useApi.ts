// Fetch-once hook for reference data that doesn't change during a session.
// Slow, user-triggered analyses use useRunner below instead.

import { useEffect, useState } from 'react'

export function useApi<T>(load: () => Promise<T>, deps: unknown[]) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setData(null); setError(null)
    load()
      .then((value) => { if (!cancelled) setData(value) })
      .catch((e: Error) => { if (!cancelled) setError(e.message) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { data, error }
}

/** An imperative runner for the slow, button-triggered analyses. */
export function useRunner<T>() {
  const [data, setData] = useState<T | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function run(load: () => Promise<T>) {
    setBusy(true); setError(null)
    try {
      setData(await load())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return { data, busy, error, run, reset: () => setData(null) }
}
