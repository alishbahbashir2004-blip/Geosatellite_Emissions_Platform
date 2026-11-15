// Shared presentational pieces used across pages; gas-agnostic.

import type { ReactNode } from 'react'
import type { Level } from '../types'

export function Metric({ label, value, delta, deltaColor, help }: {
  label: string; value: ReactNode; delta?: ReactNode
  deltaColor?: string; help?: string
}) {
  return (
    <div className="metric">
      <div className="label">
        {label}
        {help && <span className="help" title={help}>ⓘ</span>}
      </div>
      <div className="value">{value}</div>
      {delta != null && (
        <div className="delta" style={{ color: deltaColor }}>{delta}</div>
      )}
    </div>
  )
}

// Direction follows the sign of the value, not the label wording — distinct
// from the level band's own colour, which signals severity.
const DELTA_GREEN = '#09ab3b'
const DELTA_RED = '#ff2b2b'

export function LevelDelta({ level, value }: {
  level?: string | null; value?: number | null
}) {
  if (!level) return null
  const below = typeof value === 'number' && value < 0
  return (
    <span style={{ color: below ? DELTA_GREEN : DELTA_RED }}>
      {below ? '\u2193' : '\u2191'} {level}
    </span>
  )
}

export function Metrics({ children }: { children: ReactNode }) {
  return <div className="metrics">{children}</div>
}

/** Prose from config.py, which is written as HTML and belongs to the data. */
export function Callout({ html, tone = 'info', children }: {
  html?: string; tone?: 'info' | 'warn' | 'stop'; children?: ReactNode
}) {
  return (
    <div className={`callout ${tone}`}>
      {html ? <span dangerouslySetInnerHTML={{ __html: html }} /> : children}
    </div>
  )
}

export function Html({ html, className }: { html: string; className?: string }) {
  return <div className={className} dangerouslySetInnerHTML={{ __html: html }} />
}

export function Caption({ children }: { children: ReactNode }) {
  return <div className="caption">{children}</div>
}

export function Working({ what }: { what: string }) {
  return <div className="working"><span className="spinner" />{what}</div>
}

export function Tabs({ tabs, active, onChange }: {
  tabs: { id: string; label: string }[]
  active: string
  onChange: (id: string) => void
}) {
  return (
    <div className="tabs">
      {tabs.map((tab) => (
        <button key={tab.id}
                className={tab.id === active ? 'active' : ''}
                onClick={() => onChange(tab.id)}>
          {tab.label}
        </button>
      ))}
    </div>
  )
}

/** The level table as a colour key, drawn from the bands the gas declared. */
export function LevelKey({ levels, unit, title, digits = 0 }: {
  levels: Level[]; unit: string; title: string; digits?: number
}) {
  // "%" reads wrong with a leading space; a real unit needs one.
  const gap = unit === '%' ? '' : ' '
  let lower: number | null = null
  return (
    <div style={{ fontSize: '.82rem', border: '1px solid var(--hairline)',
                  borderRadius: 8, padding: '10px 14px', maxWidth: 420 }}>
      <div style={{ fontWeight: 600, paddingBottom: 4 }}>{title}</div>
      {levels.map((level, i) => {
        const span = level.upper === null
          ? `> ${lower?.toFixed(digits)}`
          : lower === null
            ? `≤ ${level.upper.toFixed(digits)}`
            : `${lower.toFixed(digits)} to ${level.upper.toFixed(digits)}`
        lower = level.upper
        return (
          <div key={i} style={{ display: 'flex', alignItems: 'center',
                                gap: 8, padding: '3px 0' }}>
            <span style={{ width: 12, height: 12, borderRadius: 3,
                           flex: 'none', background: level.color }} />
            <span style={{ flex: 1 }}>{level.label}</span>
            <span style={{ opacity: .6 }}>{span}{gap}{unit}</span>
          </div>
        )
      })}
    </div>
  )
}

export function fmt(value: unknown, digits = 2, signed = false): string {
  if (value === null || value === undefined || typeof value !== 'number'
      || !Number.isFinite(value)) return '—'
  const text = value.toFixed(digits)
  return signed && value > 0 ? `+${text}` : text
}
