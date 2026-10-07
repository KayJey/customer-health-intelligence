import { useEffect, useState } from 'react'
import { IS_STATIC, staticGet, staticPost } from './staticApi.js'

export { IS_STATIC }

export async function get(path) {
  if (IS_STATIC) return staticGet(path)
  const r = await fetch(`/api${path}`)
  if (!r.ok) throw new Error(`${path}: ${r.status}`)
  return r.json()
}

export async function post(path, body) {
  if (IS_STATIC) return staticPost(path, body)
  const r = await fetch(`/api${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  const j = await r.json()
  if (!r.ok) throw new Error(j.error || `${path}: ${r.status}`)
  return j
}

// Load a GET endpoint; reload when the path changes.
export function useApi(path) {
  const [state, set] = useState({ data: null, error: null })
  useEffect(() => {
    let live = true
    set({ data: null, error: null })
    get(path).then(data => live && set({ data, error: null })).catch(error => live && set({ data: null, error: error.message }))
    return () => { live = false }
  }, [path])
  return state
}

export const money = n => (n == null ? '-' : n >= 1e6 ? `$${(n / 1e6).toFixed(2)}M` : n >= 1e3 ? `$${Math.round(n / 1e3)}K` : `$${Math.round(n)}`)
export const pct = n => (n == null ? '-' : `${Math.round(n * 100)}%`)
export const weekLabel = d => new Date(d + 'T00:00:00').toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
export const words = t => (t || '').split(';').filter(Boolean).map(x => x.replace(/_/g, ' ').replace(/(\d+)pct/, '$1%')).join(', ') || 'none'

const FLAG = { Healthy: 'p-g', Watch: 'p-a', 'At risk': 'p-r' }
export const Flag = ({ flag, children }) => <span className={`pill ${FLAG[flag] || 'p-n'}`}>{children ?? flag}</span>
export const Sev = ({ s }) => <span className={`pill ${s === 'High' ? 'p-r' : s === 'Medium' ? 'p-a' : 'p-g'}`}>{s}</span>
export const scoreColor = s => (s < 60 ? 'var(--red)' : s < 75 ? 'var(--amber)' : 'var(--green)')

export const Card = ({ title, children, className = '' }) => (
  <div className={`card ${className}`}>{title && <h3>{title}</h3>}{children}</div>
)

export const Kpi = ({ label, value, delta, goodWhenUp = true }) => {
  const cls = delta == null || delta === 0 ? 'mute' : (delta > 0) === goodWhenUp ? 'up' : 'dn'
  return (
    <div className="card kpi"><h3>{label}</h3><b>{value}</b>
      {delta != null && <span className={cls}>{delta > 0 ? '+' : ''}{delta} vs 4 wks ago</span>}
    </div>
  )
}

export const Bar = ({ value, color }) => (
  <div className="bar"><i style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: color || scoreColor(value) }} /></div>
)

export const Loading = ({ state }) =>
  state.error ? <div className="card err">Could not load data: {state.error}. Is the backend running on port 5001?</div> : <div className="card mute">Loading...</div>

export const Note = ({ children }) => <div className="note">{children}</div>
