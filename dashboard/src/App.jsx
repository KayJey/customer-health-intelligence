import { useState } from 'react'
import { Overview, Customers, CustomerDetail } from './screens1.jsx'
import { Cohorts, Journeys, Alerts, Program } from './screens2.jsx'
import { Copilot, ThoughtSpot, Tools } from './screens3.jsx'
import { TsHub } from './TsHub.jsx'

const NAV = [
  ['hub', 'Analytics (ThoughtSpot)'], ['overview', 'Portfolio overview'], ['customers', 'Customers'], ['detail', 'Customer detail'], ['cohorts', 'Cohorts and RFM'],
  ['journeys', 'Journeys and plays'], ['alerts', 'Alerts'], ['program', 'Program impact'], ['copilot', 'AI Copilot'], ['tools', 'Copilot tools'], ['thoughtspot', 'Integration design'],
]

export default function App() {
  const [view, setView] = useState('hub')
  const [cid, setCid] = useState('C0018')
  const open = id => { setCid(id); setView('detail') }
  const screens = {
    hub: <TsHub />, overview: <Overview open={open} />, customers: <Customers open={open} />, detail: <CustomerDetail cid={cid} setCid={setCid} />,
    cohorts: <Cohorts open={open} />, journeys: <Journeys />, alerts: <Alerts open={open} />, program: <Program />,
    copilot: <Copilot />, tools: <Tools />, thoughtspot: <ThoughtSpot />,
  }
  return (
    <div className="app">
      <nav>
        <h1>Customer Health<br />Intelligence</h1>
        <div className="tag">Synthetic data</div>
        {NAV.map(([k, label]) => <button key={k} className={view === k ? 'on' : ''} onClick={() => setView(k)}>{label}</button>)}
      </nav>
      <main>{screens[view]}</main>
    </div>
  )
}
