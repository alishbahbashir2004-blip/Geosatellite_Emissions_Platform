// Renders a Vega-Lite spec (built server-side with Altair) via vega-embed.

import { useEffect, useRef } from 'react'
import embed, { type VisualizationSpec } from 'vega-embed'
import type { VegaSpec } from '../types'

export function VegaChart({ spec, height }: { spec: VegaSpec; height?: number }) {
  const host = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!spec || !host.current) return
    let view: { finalize: () => void } | null = null
    let cancelled = false

    // `width: container` makes the chart follow its box; height stays as
    // given unless the caller overrides it.
    const sized = { ...spec, width: 'container', ...(height ? { height } : {}) }

    embed(host.current, sized as VisualizationSpec, {
      actions: false,
      renderer: 'canvas',
      config: { background: 'transparent' },
    })
      .then((result) => {
        if (cancelled) result.view.finalize()
        else view = result.view
      })
      .catch(() => { /* a spec that will not render is left blank, not thrown */ })

    return () => { cancelled = true; view?.finalize() }
  }, [spec, height])

  if (!spec) return null
  return <div className="chart" ref={host} />
}
