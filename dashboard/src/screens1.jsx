import { useState } from 'react'
import { Area, AreaChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { TsCustomerCard } from './TsHub.jsx'
import { Bar, Card, Flag, Kpi, Loading, Note, get, money, pct, post, scoreColor, useApi, weekLabel, words } from './ui.jsx'

const axis = { stroke: '#8e9ac0', fontSize: 11 }
const tip = { contentStyle: { background: '#121a30', border: '1px solid #25304f', borderRadius: 8 }, labelStyle: { color: '#8e9ac0' } }

export function Overview({ open }) {
  const s = useApi('/overview')
  if (!s.data) return <Loading state={s} />
  const { kpis: k, vs_4_weeks_ago: p, distribution: dist, trend, movers } = s.data
  const total = dist.reduce((a, d) => a + d.n, 0)
  return (
    <>
      <h2>Portfolio overview</h2>
      <div className="sub">Tech Touch segment, snapshot {s.data.snapshot}. The question this answers: where is retention at risk, and what should the team do first?</div>
      <div className="row kpis">
        <Kpi label="Active customers" value={k.active_customers} />
        <Kpi label="Avg health" value={k.avg_health} delta={+(k.avg_health - p.avg_health).toFixed(1)} />
        <Kpi label="At risk" value={k.at_risk_customers} delta={k.at_risk_customers - p.at_risk} goodWhenUp={false} />
        <Kpi label="ARR at risk" value={money(k.arr_at_risk)} />
        <Kpi label="Median days to first value" value={`${k.median_days_to_first_value} d`} />
        <Kpi label="Logo retention (12 mo)" value={`${k.logo_retention_pct}%`} />
      </div>
      <div className="row g2">
        <Card title="Average health and share of customers at risk, by week">
          <ResponsiveContainer width="100%" height={230}>
            <LineChart data={trend.map(t => ({ ...t, w: weekLabel(t.week_start) }))}>
              <CartesianGrid stroke="#25304f" strokeDasharray="3 3" />
              <XAxis dataKey="w" {...axis} interval={5} /><YAxis yAxisId="a" domain={[50, 100]} {...axis} /><YAxis yAxisId="b" orientation="right" {...axis} unit="%" />
              <Tooltip {...tip} />
              <Line yAxisId="a" type="monotone" dataKey="avg_health" name="Avg health" stroke="#22d3ee" strokeWidth={2.5} dot={false} />
              <Line yAxisId="b" type="monotone" dataKey="pct_at_risk" name="% at risk" stroke="#f87171" strokeWidth={2} strokeDasharray="4 4" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Health distribution (active customers)">
          {['Healthy', 'Watch', 'At risk'].map(f => {
            const d = dist.find(x => x.health_flag === f) || { n: 0, arr: 0 }
            return (
              <div className="dim" key={f} style={{ gridTemplateColumns: '90px 1fr 120px' }}>
                <Flag flag={f} /><Bar value={(d.n / total) * 100} color={f === 'Healthy' ? 'var(--green)' : f === 'Watch' ? 'var(--amber)' : 'var(--red)'} />
                <span>{d.n} | {money(d.arr)}</span>
              </div>
            )
          })}
          <div className="mute" style={{ marginTop: 10, fontSize: 12 }}>Healthy 75 and above, Watch 60 to 74, At risk below 60. {k.expansion_candidates} customers use over 85% of their seats (expansion signal).</div>
        </Card>
      </div>
      <Card title="Biggest movers in the last 4 weeks">
        <table><thead><tr><th>Customer</th><th>Tier</th><th>ARR</th><th>Health</th><th>Change</th><th>Main driver</th><th>Warning signs</th></tr></thead>
          <tbody>{movers.map(m => (
            <tr key={m.customer_id} className="click" onClick={() => open(m.customer_id)}>
              <td>{m.customer_id}</td><td>{m.tier}</td><td>{money(m.arr_current)}</td><td style={{ color: scoreColor(m.health_score) }}>{m.health_score}</td>
              <td className={m.score_change_4w < 0 ? 'dn' : 'up'}>{m.score_change_4w > 0 ? '+' : ''}{m.score_change_4w}</td><td>{m.top_driver}</td><td className="mute">{words(m.driver_tags)}</td>
            </tr>))}</tbody></table>
      </Card>
    </>
  )
}

export function Customers({ open }) {
  const [f, setF] = useState({ flag: '', tier: '', band: '', stage: '', sort: 'health_score', order: 'asc', search: '' })
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString()
  const s = useApi(`/customers?limit=60&${qs}`)
  const set = (k, v) => setF({ ...f, [k]: v })
  // Plain function (not a component) so the dropdowns are not re-created on every state change.
  const sel = (k, label, opts) => (
    <select key={k} value={f[k]} onChange={e => set(k, e.target.value)}><option value="">{label}</option>{opts.map(o => <option key={o}>{o}</option>)}</select>
  )
  return (
    <>
      <h2>Customers</h2>
      <div className="sub">Filter by risk, coverage tier, size and lifecycle stage. Click a row for the full picture.</div>
      <div className="filters">
        <input placeholder="Search id" value={f.search} onChange={e => set('search', e.target.value)} />
        {sel('flag', 'Any health', ['At risk', 'Watch', 'Healthy'])}
        {sel('tier', 'Any tier', ['Digital', 'Pooled', 'CSM-led'])}
        {sel('band', 'Any size', ['SME', 'Mid', 'Whale'])}
        {sel('stage', 'Any stage', ['Onboarding', 'Adoption', 'Renewal', 'Expansion'])}
        <select value={`${f.sort}:${f.order}`} onChange={e => { const [sort, order] = e.target.value.split(':'); setF({ ...f, sort, order }) }}>
          <option value="health_score:asc">Lowest health first</option><option value="arr_current:desc">Largest ARR first</option>
          <option value="days_to_renewal:asc">Renewing soonest</option><option value="score_change_4w:asc">Biggest drop first</option>
        </select>
      </div>
      {!s.data ? <Loading state={s} /> : (
        <Card title={`${s.data.count} customers`}>
          <table><thead><tr><th>Customer</th><th>Industry</th><th>Size</th><th>Tier</th><th>Stage</th><th>ARR</th><th>Health</th><th>4-wk change</th><th>Renews in</th><th>RFM</th><th>Warning signs</th></tr></thead>
            <tbody>{s.data.customers.map(c => (
              <tr key={c.customer_id} className="click" onClick={() => open(c.customer_id)}>
                <td>{c.customer_id}</td><td>{c.industry}</td><td>{c.size_band}</td><td>{c.tier}</td><td>{c.lifecycle_stage}</td><td>{money(c.arr_current)}</td>
                <td><Flag flag={c.health_flag}>{c.health_score}</Flag></td>
                <td className={c.score_change_4w < 0 ? 'dn' : 'up'}>{c.score_change_4w ?? '-'}</td><td>{c.days_to_renewal} d</td><td>{c.rfm_segment}</td><td className="mute">{words(c.driver_tags)}</td>
              </tr>))}</tbody></table>
        </Card>
      )}
    </>
  )
}

const DIMS = [['adoption', 'Adoption', 30], ['support', 'Support', 20], ['engagement', 'Engagement', 20], ['commercial', 'Commercial and relationship', 20], ['onboarding', 'Onboarding', 10]]

export function CustomerDetail({ cid, setCid }) {
  const s = useApi(`/customers/${cid}`)
  const [draft, setDraft] = useState(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [pick, setPick] = useState(cid)
  if (!s.data) return <><div className="filters"><input value={pick} onChange={e => setPick(e.target.value)} /><button className="btn" onClick={() => setCid(pick)}>Open</button></div><Loading state={s} /></>
  const { customer: c, health: h, history, usage, contacts, tickets, timeline, recommendation: rec } = s.data
  const gen = async () => { setBusy(true); setMsg(''); try { setDraft(await get(`/customers/${cid}/outreach-draft`)) } catch (e) { setMsg(e.message) } setBusy(false) }
  const queue = async () => { try { const r = await post('/approvals', { customer_id: cid, subject: draft.subject, body: draft.body }); setMsg(`Queued for approval (#${r.approval_id}). Nothing was sent.`) } catch (e) { setMsg(e.message) } }
  return (
    <>
      <div className="filters"><input value={pick} onChange={e => setPick(e.target.value)} style={{ width: 110 }} /><button className="btn o" onClick={() => setCid(pick)}>Open another</button></div>
      <h2>{c.customer_id} {h && <Flag flag={h.health_flag}>Health {h.health_score}</Flag>} <span className="pill p-b">{c.tier}</span> <span className="pill p-v">{c.lifecycle_stage}</span></h2>
      <div className="sub">{c.industry} | {c.size_band} | {money(c.arr_current)} ARR | signed {c.signup_date} | renews {c.next_renewal_date || '-'} | CSM: {c.csm_owner}{c.status === 'churned' && ` | CHURNED ${c.churn_date}`}</div>
      {h && (
        <div className="row g2">
          <Card title="Score breakdown (weight)">
            {DIMS.map(([k, label, w]) => (
              <div className="dim" key={k}><span>{label} <span className="mute">({w}%)</span></span><Bar value={h[`score_${k}`]} /><span>{Math.round(h[`score_${k}`])}</span></div>
            ))}
            <div className="mute" style={{ fontSize: 12 }}>Warning signs: {words(h.driver_tags)}. Weakest area: {h.top_driver}.</div>
          </Card>
          <Card title="Recommended next action">
            <p style={{ margin: '0 0 6px' }}><span className="pill p-v">{rec.action}</span></p>
            <p className="mute" style={{ margin: 0 }}>{rec.why}</p>
            <div style={{ marginTop: 12 }}><button className="btn" onClick={gen} disabled={busy}>{busy ? 'Drafting...' : 'Draft outreach'}</button></div>
          </Card>
        </div>
      )}
      {draft && (
        <Card title={`Outreach draft (${draft.source || 'AI'})`}>
          <div className="draft">{`To: ${draft.to || '-'}\nSubject: ${draft.subject || ''}\n\n${draft.body || draft.draft}`}</div>
          <div style={{ marginTop: 8, display: 'flex', gap: 8, alignItems: 'center' }}>
            <button className="btn" onClick={queue}>Queue for approval</button><span className="mute">{msg || 'Draft only. Nothing is sent without a human.'}</span>
          </div>
        </Card>
      )}
      <div className="row g11" style={{ marginTop: 12 }}>
        <Card title="Health over time">
          <ResponsiveContainer width="100%" height={210}>
            <LineChart data={history.map(x => ({ ...x, w: weekLabel(x.week_start) }))}>
              <CartesianGrid stroke="#25304f" strokeDasharray="3 3" /><XAxis dataKey="w" {...axis} interval="preserveStartEnd" /><YAxis domain={[0, 100]} {...axis} /><Tooltip {...tip} />
              <ReferenceLine y={75} stroke="#34d399" strokeDasharray="4 4" /><ReferenceLine y={60} stroke="#f87171" strokeDasharray="4 4" />
              <Line type="monotone" dataKey="health_score" name="Health" stroke="#22d3ee" strokeWidth={2.5} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </Card>
        <Card title="Active users vs licensed seats">
          <ResponsiveContainer width="100%" height={210}>
            <AreaChart data={usage.map(x => ({ ...x, w: weekLabel(x.week_start) }))}>
              <CartesianGrid stroke="#25304f" strokeDasharray="3 3" /><XAxis dataKey="w" {...axis} interval="preserveStartEnd" /><YAxis {...axis} /><Tooltip {...tip} />
              <Area type="monotone" dataKey="seats_licensed" name="Seats" stroke="#8e9ac0" fill="#8e9ac033" /><Area type="monotone" dataKey="active_users" name="Active users" stroke="#22d3ee" fill="#22d3ee44" />
            </AreaChart>
          </ResponsiveContainer>
        </Card>
      </div>
      <div className="row g11">
        <Card title="Timeline"><table><tbody>{timeline.map((t, i) => <tr key={i}><td className="mute" style={{ whiteSpace: 'nowrap' }}>{t.date}</td><td>{t.text}</td></tr>)}</tbody></table></Card>
        <Card title="Contacts">
          <table><tbody>{contacts.map(p => <tr key={p.name}><td>{p.name}</td><td className="mute">{p.role}{p.is_champion ? ' (champion)' : ''}</td><td>{p.is_active ? <span className="pill p-g">active</span> : <span className="pill p-r">left {p.left_date}</span>}</td></tr>)}</tbody></table>
          <h3 style={{ marginTop: 14 }}>Recent tickets</h3>
          <table><tbody>{tickets.slice(0, 4).map(t => <tr key={t.ticket_id}><td className="mute">{t.created_at.slice(0, 10)}</td><td>{t.subject}</td><td>{t.escalated ? <span className="pill p-r">escalated</span> : t.reopen_count > 0 ? <span className="pill p-a">reopened</span> : ''}</td></tr>)}</tbody></table>
        </Card>
      </div>
      <TsCustomerCard cid={cid} />
      <Note>Data source: health_current, health_weekly, weekly_usage, contacts, tickets (BigQuery dataset customer_health; read locally from SQLite in this build). Utilisation {pct(h?.seat_utilisation)}.</Note>
    </>
  )
}
