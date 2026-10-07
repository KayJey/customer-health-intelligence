import { useEffect, useRef, useState } from 'react'
import { Card, Loading, Note, post, useApi } from './ui.jsx'

const sleep = ms => new Promise(r => setTimeout(r, ms))

export function Copilot() {
  const dq = useApi('/copilot/demo-questions')
  const [msgs, setMsgs] = useState([{ cls: 'bot', text: 'I can query customer data, search tickets and call notes, explain scores, draft outreach and record alert rules. Pick a question, or type your own.' }])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const end = useRef(null)
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs])
  const ask = async (question, demo_id) => {
    if (busy || !question.trim()) return
    setBusy(true); setText('')
    setMsgs(m => [...m, { cls: 'u', text: question }])
    try {
      const r = await post('/copilot', { question, demo_id })
      for (const t of r.trace || []) {
        await sleep(650)
        setMsgs(m => [...m, { cls: 'trace', tool: t.tool, input: t.input, summary: t.summary }])
      }
      await sleep(500)
      setMsgs(m => [...m, { cls: 'bot', text: r.answer }])
    } catch (e) { setMsgs(m => [...m, { cls: 'bot', text: `Error: ${e.message}` }]) }
    setBusy(false)
  }
  const demo = dq.data?.demo
  return (
    <>
      <h2>AI Copilot</h2>
      <div className="sub">Ask in plain English. The copilot chooses tools (SQL, hybrid search, compute, LLM, actions), runs them, and answers only from what they return.</div>
      {demo && <div className="banner">Demo mode: no API key is configured, so answers are recorded. The tool calls and every number were computed by the real tools on this dataset; the wording is templated, not written by an LLM. Add a key to <code>backend/.env</code> for live answers.</div>}
      <div className="row g21">
        <Card title="Conversation">
          <div className="chat">
            {msgs.map((m, i) => m.cls === 'trace'
              ? <div className="trace" key={i}>tool: {m.tool}({JSON.stringify(m.input)}) <span>→ {m.summary}</span></div>
              : <div className={`msg ${m.cls}`} key={i}>{m.text}</div>)}
            <div ref={end} />
          </div>
          <form className="ask" onSubmit={e => { e.preventDefault(); ask(text) }}>
            <input placeholder="Ask in plain English" value={text} onChange={e => setText(e.target.value)} disabled={busy} />
            <button className="btn" disabled={busy}>Ask</button>
          </form>
        </Card>
        <Card title="Try asking">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {(dq.data?.questions || []).map(q => <button key={q.id} className="chip" style={{ textAlign: 'left' }} disabled={busy} onClick={() => ask(q.question, q.id)}>{q.question}</button>)}
          </div>
          <p className="mute" style={{ fontSize: 12, marginTop: 12 }}>Drafts are drafts: nothing is ever sent. Alert rules and handoffs are recorded for a human to confirm.</p>
        </Card>
      </div>
    </>
  )
}

export function Tools() {
  const t = useApi('/copilot/tools')
  const [kind, setKind] = useState('all')
  if (!t.data) return <Loading state={t} />
  const kinds = ['all', 'sql', 'vector', 'compute', 'llm', 'action']
  const rows = t.data.filter(x => kind === 'all' || x.kind === kind)
  return (
    <>
      <h2>Copilot tools</h2>
      <div className="sub">The catalog the model sees. It picks tools, we run them, and the results go back to the model, for up to 5 turns, before it answers.</div>
      <div className="row g11">
        <Card title="How a question is answered">
          <div className="flow">
            {[['t', '1. Question', 'plain English'], ['c', '2. Model picks tools', 'from this catalog'], ['a', '3. Tool runs', 'SQL, search, compute, action'], ['c', '4. Result back to model', 'repeat up to 5 turns'], ['a', '5. Grounded answer', 'cites the numbers returned']].map(([c, a, b], i, arr) => (
              <span key={i} style={{ display: 'contents' }}><div className={`node ${c}`}>{a}<small>{b}</small></div>{i < arr.length - 1 && <span className="arrow">→</span>}</span>))}
          </div>
        </Card>
        <Card title="Data the tools reach">
          <div className="stores" style={{ gridTemplateColumns: '1fr 1fr' }}>
            <div><span className="badge k-sql">STRUCTURED</span><div className="mute">health, usage, tickets, plays (SQL)</div></div>
            <div><span className="badge k-vector">UNSTRUCTURED</span><div className="mute">ticket threads, call notes, QBR notes (vector + keyword)</div></div>
            <div><span className="badge k-compute">COMPUTE</span><div className="mute">cohorts, RFM, play lift, next action</div></div>
            <div><span className="badge k-action">ACTIONS</span><div className="mute">record-only until n8n is connected</div></div>
          </div>
        </Card>
      </div>
      <Card title={`Tool catalog (${t.data.length})`}>
        <div className="chips" style={{ marginBottom: 10 }}>{kinds.map(k => <button key={k} className={`chip ${kind === k ? 'on' : ''}`} onClick={() => setKind(k)}>{k}</button>)}</div>
        <table><thead><tr><th>Tool</th><th>Type</th><th>What it does</th><th>Example question</th></tr></thead>
          <tbody>{rows.map(x => <tr key={x.name}><td><code>{x.name}</code></td><td><span className={`badge k-${x.kind}`}>{x.kind.toUpperCase()}</span></td><td>{x.description}</td><td className="mute">{x.example}</td></tr>)}</tbody></table>
      </Card>
    </>
  )
}

const STEPS = [
  ['done', 'Data in BigQuery', 'Dataset customer_health, 21 tables, loaded'],
  ['done', 'ThoughtSpot connection', 'customer_health_bq connected: 20 tables, 199 columns (documents excluded)'],
  ['done', 'Model: Customer Health', 'health_current + customers (1:1 on customer_id), 34 columns, 2 formulas. Verified: ARR at risk 1.78M and 21 at-risk customers match this dashboard'],
  ['done', 'Liveboard: Portfolio health', '3 tiles pinned: ARR and customers at risk, ARR by health flag, at-risk customers by tier'],
  ['done', 'Embed in this dashboard', 'Liveboard renders live inside this app (verified; green badge only after ThoughtSpot confirms the render)'],
  ['todo', 'Copilot tool and n8n', 'ask_thoughtspot tool and the daily digest are still to do'],
]

const BOARDS = [
  ['Portfolio health', 'Executives and the Customer Outcomes lead', ['Customers by health flag', 'ARR at risk by tier and size', 'Average health trend', 'Biggest movers']],
  ['Program performance', 'The digital program owner (the measurement duty in the role)', ['Time to first value by tier', 'Feature activation and seat utilisation', 'Digital-influenced retention', 'Play lift vs control, A/B results']],
  ['Cohorts and retention', 'CS leadership and Finance', ['Retention by signup quarter', 'SME vs Mid vs Whale', 'Net and gross revenue retention', 'RFM segments']],
  ['Risk and renewals', 'The Tech Touch team and CSMs', ['Renewals by health', 'Open escalations and reopened tickets', 'Champion changes', 'Expansion signals']],
]

const METRICS = [
  ['ARR at risk', "SUM(arr_current) where health_flag = 'At risk'"], ['Utilisation', 'SUM(active_users) / SUM(seats_licensed)'],
  ['Time to first value', 'AVG(days_from_signup) for milestone shared_by_second_user'], ['Net revenue retention', 'ARR now / ARR at start, same accounts'],
  ['Play lift vs control', 'AVG(delta_4w) treated minus AVG(delta_4w) control'], ['Escalation rate', 'SUM(escalated) / COUNT(tickets), last 8 weeks'],
]

const SNIPPET = `// src/TsEmbed.jsx
import { AuthType, init } from '@thoughtspot/visual-embed-sdk'
import { LiveboardEmbed } from '@thoughtspot/visual-embed-sdk/react'

init({ thoughtSpotHost: 'https://team1.thoughtspot.cloud', authType: AuthType.None })  // dev only

<LiveboardEmbed liveboardId="<portfolio-health-guid>" frameParams={{ height: '640px' }}
  onLiveboardRendered={() => setState('rendered')} />`

export function ThoughtSpot() {
  return (
    <>
      <h2>Integration design</h2>
      <div className="sub">ThoughtSpot is the BI and AI analytics layer on the same BigQuery data. The BigQuery connection, Model, Liveboard and embed are live and verified. The copilot tool, n8n digest and the other Liveboards are still design.</div>
      <Card title="Status">
        <div className="flow">{STEPS.map(([s, a, b], i) => (
          <span key={i} style={{ display: 'contents' }}><div className={`node ${s === 'done' ? 'a' : 'c'}`}>{s === 'done' ? '✓ ' : '○ '}{a}<small>{b}</small></div>{i < STEPS.length - 1 && <span className="arrow">→</span>}</span>))}
        </div>
      </Card>
      <Card title="How the pieces connect">
        <div className="flow">
          {[['t', 'Synthetic data', 'generator + analytics'], ['a', 'BigQuery', 'customer_health'], ['c', 'ThoughtSpot connection', 'live query'], ['c', 'Model', 'joins and metrics'], ['a', 'Liveboards + Spotter', 'dashboards and plain-English search']].map(([c, a, b], i, arr) => (
            <span key={i} style={{ display: 'contents' }}><div className={`node ${c}`}>{a}<small>{b}</small></div>{i < arr.length - 1 && <span className="arrow">→</span>}</span>))}
        </div>
        <div className="flow" style={{ marginLeft: 32 }}>
          <div className="node a">Embedded in this dashboard<small>Visual Embed SDK</small></div>
          <div className="node a">Copilot tool<small>ask_thoughtspot (API or MCP)</small></div>
          <div className="node a">n8n digest<small>snapshot into the daily alert</small></div>
        </div>
        <div className="mute" style={{ fontSize: 12 }}>The data is queried live in BigQuery, not copied. ThoughtSpot covers structured analytics. The copilot keeps unstructured search (tickets and notes), actions and the health-score logic.</div>
      </Card>
      <div className="row g11">
        <Card title="Model: tables and metrics">
          <div className="mute" style={{ marginBottom: 8 }}>Tables joined on <code>customer_id</code>: customers, health_current, health_weekly, weekly_usage, tickets, play_runs, contract_events, onboarding_milestones.</div>
          <table><tbody>{METRICS.map(m => <tr key={m[0]}><td><b>{m[0]}</b></td><td className="mute"><code>{m[1]}</code></td></tr>)}</tbody></table>
          <div className="mute" style={{ marginTop: 8, fontSize: 12 }}>Defined once in the Model, so every chart and every Spotter answer uses the same definition.</div>
        </Card>
        <Card title="Spotter: plain-English questions it should answer">
          <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.9 }}>
            {['ARR at risk by tier', 'Retention by signup quarter', 'Time to first value by size band', 'Which plays improved utilisation vs control?', 'Customers with a champion change and renewal under 120 days', 'Escalation rate by tier last quarter'].map(q => <li key={q}>{q}</li>)}
          </ul>
        </Card>
      </div>
      <Card title="Liveboards to build">
        <table><thead><tr><th>Liveboard</th><th>Audience</th><th>What it shows</th></tr></thead>
          <tbody>{BOARDS.map(b => <tr key={b[0]}><td><b>{b[0]}</b></td><td>{b[1]}</td><td className="mute">{b[2].join(' | ')}</td></tr>)}</tbody></table>
      </Card>
      <div className="row" style={{ marginTop: 12 }}>
        <Card title="Embed code (as used in this app)">
          <pre className="draft" style={{ fontSize: 11.5, margin: 0, overflow: 'auto' }}>{SNIPPET}</pre>
        </Card>
      </div>
      <Note>What stays in this app: unstructured search over tickets and notes, the health-score logic, lifecycle plays and record-only actions. What ThoughtSpot adds: governed metrics, self-serve exploration for non-technical users, and plain-English questions on the same data.</Note>
    </>
  )
}
