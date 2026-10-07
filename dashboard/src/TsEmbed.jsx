import { useState, useSyncExternalStore } from 'react'
import { AuthType, init } from '@thoughtspot/visual-embed-sdk'
import { LiveboardEmbed, SearchEmbed, SpotterEmbed } from '@thoughtspot/visual-embed-sdk/react'

// Not secrets: the ThoughtSpot host and the ids of the Liveboard and Model. Override with VITE_TS_* variables.
export const TS_HOST = import.meta.env.VITE_TS_HOST || 'https://team1.thoughtspot.cloud'
export const TS_LIVEBOARD_ID = import.meta.env.VITE_TS_LIVEBOARD_ID || '4d9ae2ec-16e1-49ea-8f77-a85ed5cbfa7b'
export const TS_MODEL_ID = import.meta.env.VITE_TS_MODEL_ID || '1cded037-9c4f-40d1-a147-ef531a130a66'

let initialised = false
export function ensureInit() {
  if (initialised) return
  // AuthType.None: ThoughtSpot shows its own sign-in inside the frame. Development only (production would use trusted auth).
  init({ thoughtSpotHost: TS_HOST, authType: AuthType.None })
  initialised = true
}

// ---- shared connection status, so every screen shows the same truth ----
// idle | loading | signin | connected | error. 'connected' only after ThoughtSpot itself confirms an authenticated render.
let status = { state: 'idle', detail: '' }
const subs = new Set()
const setStatus = (state, detail = '') => { status = { state, detail }; subs.forEach(f => f()) }
export const useTsStatus = () => useSyncExternalStore(f => { subs.add(f); return () => subs.delete(f) }, () => status)

const REMEMBER = 'ts_connected_once'
export const wasConnected = () => { try { return localStorage.getItem(REMEMBER) === '1' } catch { return false } }
const markConnected = () => { try { localStorage.setItem(REMEMBER, '1') } catch { /* private mode */ } setStatus('connected') }

const BADGE = {
  idle: ['p-n', 'ThoughtSpot: not loaded'], loading: ['p-a', 'ThoughtSpot: loading...'], signin: ['p-a', 'ThoughtSpot: sign in inside the frame'],
  connected: ['p-g', 'ThoughtSpot: connected'], error: ['p-r', 'ThoughtSpot: could not load'],
}
export function TsStatusPill() {
  const s = useTsStatus()
  const [cls, label] = BADGE[s.state]
  return <span className={`pill ${cls}`} title={s.detail}>{label}</span>
}

// Common callbacks for every embed. A 401 or sign-in message is not fatal: keep the frame so the user can sign in.
function handlers() {
  return {
    onAuthInit: () => markConnected(),
    onError: e => {
      let d = ''
      try { d = typeof e === 'string' ? e : JSON.stringify(e?.data ?? e) } catch { d = String(e) }
      console.warn('ThoughtSpot embed error', d.slice(0, 300))
      if (/401|unauthor|session|login|auth/i.test(d)) setStatus('signin')
      else setStatus('error', d.slice(0, 300))
    },
  }
}

const Help = () => (
  <div className="note" style={{ marginBottom: 10 }}>
    If the frame shows a ThoughtSpot sign-in, sign in there with your ThoughtSpot email and password (Google sign-in cannot run inside a frame).
    If it stays blank, check that <code>{window.location.origin}</code> is in ThoughtSpot's Security Settings and that your browser allows cookies for {TS_HOST.replace('https://', '')}.
  </div>
)

// Wraps an embed so it loads on click, or automatically once it has connected before.
export function TsFrame({ children, autoLoad = true, height = 640 }) {
  const s = useTsStatus()
  const [on, setOn] = useState(autoLoad && wasConnected())
  const start = () => { ensureInit(); setStatus('loading'); setOn(true) }
  if (on) ensureInit()
  return (
    <div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 10, flexWrap: 'wrap' }}>
        <TsStatusPill />
        <button className="btn" onClick={start} disabled={s.state === 'loading'}>{on ? 'Reload' : 'Load from ThoughtSpot'}</button>
        <a className="mute" href={`${TS_HOST}/#/insights/pinboard/${TS_LIVEBOARD_ID}`} target="_blank" rel="noreferrer">Open in ThoughtSpot</a>
      </div>
      {(s.state === 'signin' || s.state === 'error') && <Help />}
      {s.state === 'error' && s.detail && <div className="note err" style={{ marginBottom: 10 }}>ThoughtSpot reported: <code>{s.detail}</code></div>}
      {on ? <div style={{ minHeight: height }}>{children}</div> : <div className="mute" style={{ fontSize: 12 }}>Loads only when you click, so the rest of the app works without ThoughtSpot access.</div>}
    </div>
  )
}

export const TsLiveboard = () => (
  <LiveboardEmbed liveboardId={TS_LIVEBOARD_ID} frameParams={{ width: '100%', height: '640px' }} {...handlers()} onLiveboardRendered={() => markConnected()} />
)

export const TsSpotter = ({ query }) => (
  <SpotterEmbed
    key={query || 'blank'}
    worksheetId={TS_MODEL_ID}
    frameParams={{ width: '100%', height: '640px' }}
    searchOptions={query ? { searchQuery: query, executeSearch: true } : undefined}
    {...handlers()}
  />
)

// ThoughtSpot search tokens, e.g. "[customer_id].'C0018' [health_score]". Our app passes the context in; ThoughtSpot answers.
export const TsSearch = ({ tokens, height = 560 }) => (
  <SearchEmbed
    key={tokens}
    dataSources={[TS_MODEL_ID]}
    hideDataSources
    searchOptions={{ searchTokenString: tokens, executeSearch: true }}
    frameParams={{ width: '100%', height: `${height}px` }}
    {...handlers()}
  />
)
