// Router and sidebar. The sidebar is built from the gas registry, so a gas
// declared but not built shows greyed out and isn't routable.

import { NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { api } from './api'
import { useApi } from './useApi'
import { Dashboard } from './pages/Dashboard'
import { GasPage } from './pages/GasPage'
import { Co2Page } from './pages/Co2Page'

export function App() {
  const { data } = useApi(() => api.dashboard(), [])
  const gases = data?.gases ?? []

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">Emissions Intelligence</div>
        <div className="brand-sub">Sentinel-5P · OCO-2/3 · NASA GHG Center</div>

        <NavLink to="/" end
                 className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
          Dashboard
        </NavLink>

        <div className="section">Gas agents</div>
        {gases.map((gas) => (
          gas.live ? (
            <NavLink key={gas.key} to={`/${gas.key}`}
                     className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
              <span className="nav-dot" style={{ background: gas.accent }} />
              {gas.formula} · {gas.name}
            </NavLink>
          ) : (
            <div key={gas.key} className="nav-item" style={{ opacity: .45 }}>
              <span className="nav-dot" style={{ background: gas.accent }} />
              {gas.formula} · {gas.name}
            </div>
          )
        ))}
      </aside>

      <main className="main">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/co2" element={<Co2Page />} />
          {['ch4', 'co', 'no2', 'so2'].map((key) => (
            <Route key={key} path={`/${key}`} element={<GasPage gasKey={key} />} />
          ))}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  )
}
