import { useState } from 'react'
import { Bar as RBar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Bar, Card, Flag, Loading, Note, Sev, money, useApi, words } from './ui.jsx'

const axis = { stroke: '#8e9ac0', fontSize: 11 }
const tip = { contentStyle: { background: '#121a30', border: '1px solid #25304f', borderRadius: 8 }, labelStyle: { color: '#8e9ac0' } }
const heat = v => (v == null ? 'transparent' : v >= 95 ? '#1b6b4f' : v >= 85 ? '#2a7a4f' : v >= 78 ? '#6b6b1b' : '#7a3a1b')

const SEG_NOTE = {
  Champions: 'Recent, frequent users. Candidates for references and expansion.', 'Light users': 'Recent but low frequency. Adoption nudge targets.', Loyal: 'Steady usage.',
  Promising: 'New and ramping. Protect the onboarding.', 'Cannot lose': 'High ARR and gone quiet. Executive outreach.', 'At risk': 'Used to be active, now lapsing.',
  Hibernating: 'Little recent use.', 'Need attention': 'Slipping.',
}

export function Cohorts({ open }) {
  const c = useApi('/cohorts')
  const [seg, setSeg] = useState('')
  const r = useApi(`/rfm${seg ? `?segment=${encodeURIComponent(seg)}` : ''}`)
  if (!c.data) return <Loading state={c} />
  const cohortTable = (rows, key, label) => (
    <table><thead><tr><th>{label}</th><th>Active</th><th>Avg health</th><th>At risk</th><th>ARR at risk</th><th>Logo ret.</th><th>Net rev. ret.</th><th>Days to 1st value</th></tr></thead>
      <tbody>{rows.map(x => <tr key={x[key]}><td>{x[key]}</td><td>{x.active}/{x.customers}</td><td>{x.avg_health}</td><td>{x.at_risk}</td><td>{money(x.arr_at_risk)}</td><td>{x.logo_retention_pct}%</td><td>{x.net_retention_pct}%</td><td>{x.median_days_to_first_value}</td></tr>)}</tbody></table>
  )
  return (
    <>
      <h2>Cohorts and RFM</h2>
      <div className="sub">Who retains, who stalls, and which segment needs which level of coverage.</div>
      <div className="row g11">
        <Card title="Size cohorts: SME vs Mid vs Whales">{cohortTable(c.data.size, 'size_band', 'Cohort')}</Card>
        <Card title="Coverage tiers: where digital stops and a CSM starts">{cohortTable(c.data.tier, 'tier', 'Tier')}</Card>
      </div>
      <Card title="Logo retention by signup quarter (% of cohort still a customer)">
        <table className="heat"><thead><tr><th>Cohort</th><th>Customers</th>{['M3', 'M6', 'M9', 'M12', 'M15', 'M18'].map(m => <th key={m}>{m}</th>)}</tr></thead>
          <tbody>{c.data.retention_matrix.map(x => <tr key={x.cohort}><td>{x.cohort}</td><td>{x.customers}</td>{['M3', 'M6', 'M9', 'M12', 'M15', 'M18'].map(m => <td key={m} style={{ background: heat(x[m]) }}>{x[m] == null ? '' : x[m]}</td>)}</tr>)}</tbody></table>
        <div className="mute" style={{ fontSize: 12, marginTop: 6 }}>Contracts are annual, so churn steps at renewal dates. A cell shows only when the whole cohort has been observed that long.</div>
      </Card>
      <h3 style={{ margin: '16px 0 8px', color: 'var(--mute)', fontSize: 12, textTransform: 'uppercase', letterSpacing: '.5px' }}>RFM segments (usage-based: recency, frequency, ARR)</h3>
      {r.data && (
        <>
          <div className="segs">{r.data.summary.map(s => (
            <button key={s.rfm_segment} className={`seg ${seg === s.rfm_segment ? 'on' : ''}`} onClick={() => setSeg(seg === s.rfm_segment ? '' : s.rfm_segment)}>
              <span className="mute">{s.rfm_segment}</span><b>{s.customers}</b><span className="mute" style={{ fontSize: 12 }}>{money(s.arr)} | {SEG_NOTE[s.rfm_segment]}</span>
            </button>))}</div>
          <Card title={seg ? `${seg}: largest accounts` : 'Largest accounts, all segments'}>
            <table><thead><tr><th>Customer</th><th>Size</th><th>Tier</th><th>Segment</th><th>Last meaningful use</th><th>ARR</th><th>Health</th></tr></thead>
              <tbody>{r.data.customers.slice(0, 12).map(x => <tr key={x.customer_id} className="click" onClick={() => open(x.customer_id)}><td>{x.customer_id}</td><td>{x.size_band}</td><td>{x.tier}</td><td>{x.rfm_segment}</td><td>{x.recency_days >= 900 ? 'never' : `${x.recency_days} d ago`}</td><td>{money(x.monetary_arr)}</td><td><Flag flag={x.health_flag}>{x.health_score}</Flag></td></tr>)}</tbody></table>
          </Card>
        </>
      )}
    </>
  )
}

const FLOWS = [
  ['Onboarding stall', 'Goal: reach first value fast', [['t', 'Trigger', 'Day 14, no dashboard created'], ['c', 'Condition', 'Tier is Digital or Pooled?'], ['a', 'Digital play', 'Guided first-dashboard email'], ['c', 'Opened in 5 days?', 'Yes: send guide. No: in-app message'], ['h', 'Still stalled at day 28', 'Hand off to a CSM']]],
  ['Adoption nudge', 'Goal: lift seat utilisation', [['t', 'Trigger', 'Utilisation under 40% for 2 weeks'], ['c', 'Experiment', '25% control, rest A or B'], ['a', 'A: generic / B: personalised', 'B uses the customer\'s industry'], ['c', 'Measure at 4 weeks', 'Utilisation change vs control']]],
  ['Champion loss', 'Goal: protect the relationship', [['t', 'Trigger', 'Champion left or emails bounce'], ['c', 'Condition', 'ARR high or renewal under 120 days?'], ['h', 'Alert the CSM', 'With an AI-written account brief'], ['a', 'Outreach to other users', 'Draft, human approves']]],
  ['Renewal readiness', 'Goal: renew without surprises', [['t', 'Trigger', 'Renewal in 120 days'], ['c', 'Condition', 'Health below 75?'], ['a', 'Value summary', 'Adoption results, success plan'], ['h', 'Not healthy', 'Executive check-in']]],
]

export function Journeys() {
  const p = useApi('/plays')
  return (
    <>
      <h2>Journeys and plays</h2>
      <div className="sub">Every journey is a flow of triggers, conditions, branches and outcomes. In production each one runs as an n8n workflow; here they are logged as play runs with a control group where possible.</div>
      {FLOWS.map(([name, goal, nodes]) => (
        <Card key={name} title={`${name}: ${goal}`}>
          <div className="flow">{nodes.map(([cls, a, b], i) => <span key={i} style={{ display: 'contents' }}><div className={`node ${cls}`}>{a}<small>{b}</small></div>{i < nodes.length - 1 && <span className="arrow">→</span>}</span>)}</div>
        </Card>
      ))}
      {p.data && (
        <Card title="Play runs and measured outcomes" className="" >
          <table><thead><tr><th>Play</th><th>Group</th><th>Variant</th><th>Runs</th><th>Measured</th><th>Mean change in utilisation (4 wk)</th><th>Share improved</th></tr></thead>
            <tbody>{p.data.stats.map((s, i) => <tr key={i}><td>{s.play_id}</td><td>{s.experiment_group}</td><td>{s.variant}</td><td>{s.runs}</td><td>{s.measured}</td><td>{s.mean_delta_4w ?? '-'}</td><td>{s.improved_rate != null ? `${Math.round(s.improved_rate * 100)}%` : '-'}</td></tr>)}</tbody></table>
        </Card>
      )}
      <Note>Triggers and conditions are explicit rules, so the team can see why a customer was in or out of a play, and when a customer moves from digital to CSM-led coverage.</Note>
    </>
  )
}

export function Alerts({ open }) {
  const a = useApi('/alerts')
  if (!a.data) return <Loading state={a} />
  return (
    <>
      <h2>Alerts</h2>
      <div className="sub">The daily digest an n8n workflow would send to the Tech Touch team: {a.data.count} items for {a.data.date}, most urgent first.</div>
      <Card>
        <table><thead><tr><th>Severity</th><th>Customer</th><th>Tier</th><th>ARR</th><th>What changed</th><th>Warning signs</th><th>Suggested next step</th></tr></thead>
          <tbody>{a.data.alerts.slice(0, 25).map(x => (
            <tr key={x.customer_id + x.what_changed} className="click" onClick={() => open(x.customer_id)}>
              <td><Sev s={x.severity} /></td><td>{x.customer_id}</td><td>{x.tier}</td><td>{money(x.arr_current)}</td><td>{x.what_changed}</td><td className="mute">{words(x.driver_tags)}</td><td><span className="pill p-v">{x.next_step}</span></td>
            </tr>))}</tbody></table>
      </Card>
      <Note>An alert fires on a change of state (new At risk, slipping to Watch) or on a risk that meets a near renewal, not on every low score. Accounts whose dip recovered on its own (a migration, a quarter-end freeze) are read in the notes before anyone escalates.</Note>
    </>
  )
}

const METRICS = [
  ['Time to first value', 'Days from signup until a second user views a dashboard', 'onboarding_milestones', 'Is onboarding working?'],
  ['Feature activation', 'Share of seats active, and features used, per customer', 'weekly_usage', 'Are customers getting value, not just logging in?'],
  ['Health score and flag mix', 'Five-dimension score; Healthy, Watch, At risk', 'health_weekly', 'Where is retention at risk?'],
  ['Digital-influenced retention', 'Retention of accounts that got a play vs matched control', 'play_runs + contract_events', 'Did the program change outcomes?'],
  ['Play lift vs control', 'Utilisation change 4 weeks after a play, treated vs control', 'play_runs', 'Which plays earn their place?'],
  ['Escalations and reopens', 'Tickets escalated or reopened in the last 8 weeks', 'tickets', 'Is support friction building up?'],
  ['Net revenue retention', 'ARR now vs ARR at start for the same accounts', 'contract_events', 'Is the base growing or shrinking?'],
]

export function Program() {
  const p = useApi('/program-impact')
  const o = useApi('/overview')
  const [save, setSave] = useState(25)
  if (!p.data || !o.data) return <Loading state={p} />
  const atRisk = o.data.kpis.arr_at_risk
  const ab = p.data.adoption_nudge_ab
  const ttfv = p.data.time_to_first_value_by_tier.map(t => ({ tier: t.tier, days: t.avg_days }))
  return (
    <>
      <h2>Program impact</h2>
      <div className="sub">The metrics the digital program is run on, the evidence so far, and what the outcome could be at scale.</div>
      <Card title="Metrics this program is measured on">
        <table><thead><tr><th>Metric</th><th>Definition</th><th>Source table</th><th>Question it answers</th></tr></thead>
          <tbody>{METRICS.map(m => <tr key={m[0]}><td><b>{m[0]}</b></td><td>{m[1]}</td><td className="mute"><code>{m[2]}</code></td><td>{m[3]}</td></tr>)}</tbody></table>
      </Card>
      <div className="row g11" style={{ marginTop: 12 }}>
        <Card title="Experiment: adoption nudge, A vs B vs control">
          <table><thead><tr><th>Variant</th><th>Accounts</th><th>Mean change in utilisation</th><th>Share improved</th></tr></thead>
            <tbody>{ab.map(x => <tr key={x.variant}><td>{{ A: 'A: generic email', B: 'B: personalised by industry', control: 'Control (no nudge)' }[x.variant]}</td><td>{x.n}</td><td>{x.mean_delta > 0 ? '+' : ''}{x.mean_delta}</td><td>{Math.round(x.improved_rate * 100)}%</td></tr>)}</tbody></table>
          <div className="mute" style={{ fontSize: 12, marginTop: 6 }}>{p.data.note}</div>
        </Card>
        <Card title="Average days to first value, by coverage tier">
          <ResponsiveContainer width="100%" height={170}>
            <BarChart data={ttfv}><CartesianGrid stroke="#25304f" strokeDasharray="3 3" /><XAxis dataKey="tier" {...axis} /><YAxis {...axis} /><Tooltip {...tip} /><RBar dataKey="days" name="Days" fill="#22d3ee" radius={[4, 4, 0, 0]} /></BarChart>
          </ResponsiveContainer>
        </Card>
      </div>
      <Card title="Potential outcome (a scenario, not a measurement)">
        <div className="dim" style={{ gridTemplateColumns: '300px 1fr 70px' }}>
          <span>Share of at-risk ARR saved by earlier, proactive action</span>
          <input type="range" min="5" max="60" value={save} onChange={e => setSave(+e.target.value)} /><b>{save}%</b>
        </div>
        <p style={{ margin: '6px 0 0' }}>ARR currently flagged At risk: <b>{money(atRisk)}</b>. At a <b>{save}%</b> save rate, the program protects about <b style={{ color: 'var(--green)' }}>{money(atRisk * save / 100)}</b> of ARR per cycle,
          while scaling coverage with automation instead of headcount.</p>
        <div className="mute" style={{ fontSize: 12, marginTop: 6 }}>The save rate is an assumption you choose. In the data, the warning score dropped below 60 a median of about 7 weeks before churn, which is the window these plays work in.</div>
      </Card>
    </>
  )
}
