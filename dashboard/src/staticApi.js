// Static demo mode: no backend. Every API response was exported to /static-api/*.json by backend/export_static.py.
// Filtering and sorting that the backend does with SQL is repeated here in the browser.
export const IS_STATIC = import.meta.env.VITE_STATIC === '1'

const sj = async p => {
  const r = await fetch(`${import.meta.env.BASE_URL}static-api/${p}`)
  if (!r.ok) throw new Error(`${p}: ${r.status}`)
  return r.json()
}

const STOP = new Set('the a an of to in is are for me my our which what who how do does did can you please show give any all'.split(' '))

function matchQuestion(question, entries) {
  const q = question.toLowerCase()
  const toks = new Set((q.match(/[a-z0-9]+/g) || []).filter(t => !STOP.has(t)))
  let best = null
  let score = 0
  for (const e of entries) {
    const words = new Set(e.question.toLowerCase().match(/[a-z0-9]+/g) || [])
    const s = e.keywords.filter(k => q.includes(k)).length * 2 + [...toks].filter(t => words.has(t)).length
    if (s > score) { best = e; score = s }
  }
  return score >= 2 ? best : null
}

const SORTS = ['health_score', 'arr_current', 'days_to_renewal', 'score_change_4w', 'customer_id']

export async function staticGet(path) {
  const [p, qs] = path.split('?')
  const a = new URLSearchParams(qs || '')

  if (p === '/customers') {
    let rows = (await sj('customers.json')).customers
    const eq = (k, v) => { if (v) rows = rows.filter(r => r[k] === v) }
    eq('tier', a.get('tier'))
    eq('lifecycle_stage', a.get('stage'))
    eq('industry', a.get('industry'))
    eq('size_band', a.get('band'))
    eq('health_flag', a.get('flag'))
    const rw = a.get('renewal_within')
    if (rw) rows = rows.filter(r => r.days_to_renewal != null && r.days_to_renewal <= +rw)
    const srch = (a.get('search') || '').toLowerCase()
    if (srch) rows = rows.filter(r => r.customer_id.toLowerCase().includes(srch) || (r.company_name || '').toLowerCase().includes(srch))
    const sort = SORTS.includes(a.get('sort')) ? a.get('sort') : 'health_score'
    const dir = a.get('order') === 'desc' ? -1 : 1
    rows = [...rows].sort((x, y) => {
      if (x[sort] == null) return 1
      if (y[sort] == null) return -1
      return (x[sort] > y[sort] ? 1 : x[sort] < y[sort] ? -1 : 0) * dir
    })
    rows = rows.slice(0, +(a.get('limit') || 100))
    return { count: rows.length, customers: rows }
  }

  let m = p.match(/^\/customers\/([^/]+)\/outreach-draft$/)
  if (m) return sj(`drafts/${m[1]}.json`)
  m = p.match(/^\/customers\/([^/]+)$/)
  if (m) return sj(`customer/${m[1]}.json`)

  if (p === '/rfm') {
    const d = await sj('rfm.json')
    const seg = a.get('segment')
    return seg ? { ...d, customers: d.customers.filter(c => c.rfm_segment === seg) } : d
  }
  if (p === '/copilot/demo-questions') {
    return { demo: true, questions: (await sj('copilot_demo.json')).map(x => ({ id: x.id, question: x.question })) }
  }
  if (p === '/copilot/tools') return sj('copilot_tools.json')
  return sj(`${p.slice(1)}.json`)   // overview, cohorts, plays, alerts, program-impact
}

export async function staticPost(path, body) {
  if (path === '/copilot') {
    const e = await sj('copilot_demo.json')
    const hit = e.find(x => x.id === body.demo_id) || matchQuestion(body.question || '', e)
    return hit
      ? { demo: true, answer: hit.answer, trace: hit.trace, question: hit.question }
      : { demo: true, trace: [], answer: 'Static demo: I can only answer the recorded questions. Try one of: ' + e.map(x => x.question).join('; ') }
  }
  if (path === '/approvals') {
    return { approval_id: Math.floor(Math.random() * 900) + 100, status: 'pending', note: 'Static demo: nothing was saved or sent.' }
  }
  throw new Error('Not available in the static demo')
}
