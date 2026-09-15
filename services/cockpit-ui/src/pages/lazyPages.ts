import { lazy, type ComponentType } from 'react'

/**
 * Every page, loaded when it is first opened rather than with the app shell.
 * This is the one list of pages the router mounts.
 */
function page<K extends string>(load: () => Promise<Record<K, ComponentType>>, name: K) {
  return lazy(() => load().then((module) => ({ default: module[name] })))
}

export const Overview = page(() => import('./Overview'), 'Overview')
export const Opportunities = page(() => import('./Opportunities'), 'Opportunities')
export const OpportunityDetail = page(() => import('./OpportunityDetail'), 'OpportunityDetail')
export const Execution = page(() => import('./Execution'), 'Execution')
export const Positions = page(() => import('./Positions'), 'Positions')
export const RiskPolicies = page(() => import('./RiskPolicies'), 'RiskPolicies')
export const Settings = page(() => import('./Settings'), 'Settings')
export const Market = page(() => import('./Market'), 'Market')
export const MarketCanvas = page(() => import('./MarketCanvas'), 'MarketCanvas')
export const KnowledgeIntake = page(() => import('./KnowledgeIntake'), 'KnowledgeIntake')
export const Sources = page(() => import('./Sources'), 'Sources')
export const Copilot = page(() => import('./Copilot'), 'Copilot')
export const Autonomy = page(() => import('./Autonomy'), 'Autonomy')
export const Logs = page(() => import('./Logs'), 'Logs')
export const RegimeLab = page(() => import('./RegimeLab'), 'RegimeLab')
export const Thesis = page(() => import('./Thesis'), 'Thesis')
export const Agents = page(() => import('./Agents'), 'Agents')
export const Fleet = page(() => import('./Fleet'), 'Fleet')
export const Pipeline = page(() => import('./Pipeline'), 'Pipeline')
export const SignalLedger = page(() => import('./SignalLedger'), 'SignalLedger')
export const Timeframes = page(() => import('./Timeframes'), 'Timeframes')
