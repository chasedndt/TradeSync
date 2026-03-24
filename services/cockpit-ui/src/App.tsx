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
  Sources,
  Copilot,
  Autonomy,
  Logs,
} from './pages'

export default function App() {
  // Sync ExecutionContext with backend state (isDryRun, isDemo)
  useBackendSync()

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Overview />} />
        <Route path="/opportunities" element={<Opportunities />} />
        <Route path="/opportunities/:id" element={<OpportunityDetail />} />
        <Route path="/market" element={<Market />} />
        <Route path="/execution" element={<Execution />} />
        <Route path="/positions" element={<Positions />} />
        <Route path="/sources" element={<Sources />} />
        <Route path="/copilot" element={<Copilot />} />
        <Route path="/autonomy" element={<Autonomy />} />
        <Route path="/logs" element={<Logs />} />
        <Route path="/risk-policies" element={<RiskPolicies />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}
