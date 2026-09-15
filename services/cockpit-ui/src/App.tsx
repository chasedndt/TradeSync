import { Routes, Route } from 'react-router-dom'
import { AppShell } from './components/layout'
import { useBackendSync } from './api/hooks'
import {
  Overview,
  Opportunities,
  OpportunityDetail,
  Execution,
  Positions,
  RiskPolicies,
  Settings,
  Market,
  MarketCanvas,
  KnowledgeIntake,
  Sources,
  Copilot,
  Autonomy,
  Logs,
  RegimeLab,
  Thesis,
  Agents,
  Fleet,
  Pipeline,
  SignalLedger,
  Timeframes,
} from './pages/lazyPages'

export default function App() {
  // Sync ExecutionContext with the backend execution gate (paperOnly)
  useBackendSync()

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Overview />} />
        <Route path="/opportunities" element={<Opportunities />} />
        <Route path="/opportunities/:id" element={<OpportunityDetail />} />
        <Route path="/market" element={<Market />} />
        <Route path="/canvas" element={<MarketCanvas />} />
        <Route path="/execution" element={<Execution />} />
        <Route path="/positions" element={<Positions />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/intake" element={<KnowledgeIntake />} />
        <Route path="/copilot" element={<Copilot />} />
        <Route path="/autonomy" element={<Autonomy />} />
        <Route path="/logs" element={<Logs />} />
        <Route path="/regime-lab" element={<RegimeLab />} />
        <Route path="/thesis" element={<Thesis />} />
        <Route path="/timeframes" element={<Timeframes />} />
        <Route path="/agents" element={<Agents />} />
        <Route path="/fleet" element={<Fleet />} />
        <Route path="/signal-ledger" element={<SignalLedger />} />
        <Route path="/pipeline" element={<Pipeline />} />
        <Route path="/risk-policies" element={<RiskPolicies />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}
