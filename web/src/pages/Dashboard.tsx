// Landing page: one card per gas, driven entirely by the registry. Gases
// with live=false render greyed out instead of linking.

import { Link } from 'react-router-dom'
import { useApi } from '../useApi'
import { api } from '../api'
import { Working } from '../components/ui'

export function Dashboard() {
  const { data, error } = useApi(() => api.dashboard(), [])

  if (error) return <div className="error">{error}</div>
  if (!data) return <Working what="Loading the registry…" />

  return (
    <>
      <div className="page-head">
        <h1>Satellite Emissions Intelligence</h1>
        <p>
          Per-gas agents over satellite atmospheric data. Each measures an area
          against the region around it over the same dates, and reports whether
          it stands above its own local background rather than against a global
          average.
        </p>
      </div>

      <div className="cards">
        {data.gases.map((gas) => {
          const card = (
            <>
              <span className="formula" style={{ background: gas.accent }}>
                {gas.formula}
              </span>
              <div className="rule" style={{ background: gas.accent }} />
              <h3>{gas.name}</h3>
              <div className="meta">{gas.product}</div>
              <div className="meta">{gas.unit} · since {gas.since}</div>
              {gas.tellsYou && <p>{gas.tellsYou}</p>}
              {gas.sdgs.length > 0 && (
                <div className="meta" style={{ marginTop: '.5rem' }}>
                  {gas.sdgs.join(' · ')}
                </div>
              )}
            </>
          )
          return gas.live
            ? <Link key={gas.key} className="card" to={`/${gas.key}`}>{card}</Link>
            : <div key={gas.key} className="card dim">{card}</div>
        })}
      </div>
    </>
  )
}
