import { useState } from 'react'
import { Card, Kpi, Note, money, useApi } from './ui.jsx'
import { TsFrame, TsLiveboard, TsSearch, TsSpotter, TsStatusPill } from './TsEmbed.jsx'

const QUESTIONS = [
  'ARR at risk by tier',
  'Average health score by industry',
  'Customers with health flag At risk and days to renewal less than 90',
  'How many customers are in each rfm segment',
  'Top 10 customers by ARR with their health score',
]
const EXPLORE = [
  ['ARR by health flag and tier', '[arr_current] [health_flag] [tier]'],
  ['Health by size band', '[health_score] [size_band] [health_flag]'],
  ['At-risk detail', "[customer_id] [health_score] [top_driver] [arr_current] [health_flag].'At risk'"],
]

const TABS = [['liveboard', 'Portfolio Liveboard'], ['spotter', 'Ask Spotter'], ['explore', 'Explore (Search)']]

export function TsHub() {
  const [tab, setTab] = useState('liveboard')
  const [q, setQ] = useState('')
  const [tokens, setTokens] = useState(EXPLORE[0][1])
  const o = useApi('/overview')
  const k = o.data?.kpis
  return (
    <>
      <h2>Analytics, powered by ThoughtSpot</h2>
      <div className="sub">
        ThoughtSpot sits on the same BigQuery data as this app and is embedded here: a governed Liveboard, plain-English questions with Spotter, and free exploration.
        Our own backend adds what ThoughtSpot does not do: health scoring, lifecycle plays, unstructured search and actions.
      </div>
      {k && (
        <div className="row g3">
          <Kpi label="Customers at risk (this app, from SQLite)" value={k.at_risk_customers} />
          <Kpi label="ARR at risk (this app, from SQLite)" value={money(k.arr_at_risk)} />
          <div className="card kpi"><h3>Same numbers in ThoughtSpot</h3><b style={{ fontSize: 16 }}><TsStatusPill /></b>
            <span className="mute">Liveboard tile "ARR at Risk, At Risk Customers" should read 1.78M and 21.</span></div>
        </div>
      )}
      <div className="chips" style={{ margin: '4px 0 12px' }}>{TABS.map(([id, label]) => <button key={id} className={`chip ${tab === id ? 'on' : ''}`} onClick={() => setTab(id)}>{label}</button>)}</div>

      {tab === 'liveboard' && <Card title="Liveboard: Portfolio health (live from BigQuery through ThoughtSpot)"><TsFrame><TsLiveboard /></TsFrame></Card>}

      {tab === 'spotter' && (
        <Card title="Spotter: ask the Customer Health model in plain English">
          <div className="mute" style={{ fontSize: 12, marginBottom: 6 }}>Click a question to copy it, then paste it into Spotter below.{q && <b style={{ color: 'var(--green)' }}> Copied: {q}</b>}</div>
          <div className="chips" style={{ marginBottom: 10 }}>
            {QUESTIONS.map(x => <button key={x} className={`chip ${q === x ? 'on' : ''}`} onClick={() => { setQ(x); try { navigator.clipboard.writeText(x) } catch { /* clipboard blocked */ } }}>{x}</button>)}
          </div>
          <TsFrame><TsSpotter /></TsFrame>
        </Card>
      )}

      {tab === 'explore' && (
        <Card title="Explore: search the Customer Health model">
          <div className="chips" style={{ marginBottom: 10 }}>
            {EXPLORE.map(([label, t]) => <button key={label} className={`chip ${tokens === t ? 'on' : ''}`} onClick={() => setTokens(t)}>{label}</button>)}
          </div>
          <TsFrame><TsSearch tokens={tokens} /></TsFrame>
        </Card>
      )}

      <Note>
        Why both? ThoughtSpot gives business users governed metrics and self-serve answers on structured data. This app adds the health-score logic, the journeys and plays,
        search over tickets and call notes, and approved actions. They read the same tables, so the numbers agree.
      </Note>
    </>
  )
}

// Context handoff: this app passes the selected customer into ThoughtSpot.
export function TsCustomerCard({ cid }) {
  const tokens = `[customer_id].'${cid}' [health_score] [score_adoption] [score_support] [score_engagement] [score_commercial] [score_onboarding] [arr_current]`
  return (
    <Card title={`Analyze ${cid} in ThoughtSpot`}>
      <div className="mute" style={{ fontSize: 12, marginBottom: 8 }}>This app sends the customer id to ThoughtSpot as a search filter. Search tokens: <code>{tokens}</code></div>
      <TsFrame autoLoad={false} height={420}><TsSearch tokens={tokens} height={420} /></TsFrame>
    </Card>
  )
}
