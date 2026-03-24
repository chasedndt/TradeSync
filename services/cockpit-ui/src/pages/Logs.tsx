import { useState } from 'react'
import { FileText, Shield, AlertCircle, Clock, CheckCircle, XCircle, Filter, Activity } from 'lucide-react'
import { useMarketAlerts } from '../api/hooks'

type LogTab = 'decisions' | 'orders' | 'alerts'

export function Logs() {
  const [activeTab, setActiveTab] = useState<LogTab>('decisions')
  const { data: alerts = [] } = useMarketAlerts(100)

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Decisions & Orders</h2>
        <span className="text-xs text-gray-500">Full audit trail</span>
      </div>

      {/* Tab Selector */}
      <div className="flex gap-2">
        <button
          onClick={() => setActiveTab('decisions')}
          className={`px-4 py-2 rounded text-sm flex items-center gap-2 ${
            activeTab === 'decisions'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}
        >
          <Shield size={14} />
          Decisions
        </button>
        <button
          onClick={() => setActiveTab('orders')}
          className={`px-4 py-2 rounded text-sm flex items-center gap-2 ${
            activeTab === 'orders'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}
        >
          <FileText size={14} />
          Orders
        </button>
        <button
          onClick={() => setActiveTab('alerts')}
          className={`px-4 py-2 rounded text-sm flex items-center gap-2 ${
            activeTab === 'alerts'
              ? 'bg-blue-600 text-white'
              : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}
        >
          <Activity size={14} />
          Market Alerts
          {alerts.length > 0 && (
            <span className="bg-cyan-600 text-white text-[10px] px-1.5 py-0.5 rounded-full">
              {alerts.length}
            </span>
          )}
        </button>
      </div>

      {/* Filters */}
      <div className="card bg-gray-900/50">
        <div className="flex flex-wrap gap-4 items-center">
          <div className="flex items-center gap-2">
            <Filter size={14} className="text-gray-500" />
            <span className="text-sm text-gray-400">Filters:</span>
          </div>
          <select className="input text-sm bg-gray-800 border-gray-700">
            <option value="all">All Venues</option>
            <option value="drift">Drift</option>
            <option value="hyperliquid">Hyperliquid</option>
          </select>
          <select className="input text-sm bg-gray-800 border-gray-700">
            <option value="all">All Statuses</option>
            <option value="allowed">Allowed</option>
            <option value="blocked">Blocked</option>
          </select>
          <input
            type="date"
            className="input text-sm bg-gray-800 border-gray-700"
          />
        </div>
      </div>

      {/* Decisions Tab */}
      {activeTab === 'decisions' && (
        <div className="card">
          <h3 className="text-sm font-medium text-gray-400 mb-4">Risk Decisions</h3>

          {/* Table Header */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Time</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Opportunity</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Venue</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Verdict</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Reason</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Trace ID</th>
                </tr>
              </thead>
              <tbody>
                {/* Empty State */}
                <tr>
                  <td colSpan={6} className="py-12 text-center">
                    <div className="flex flex-col items-center">
                      <AlertCircle size={32} className="text-gray-700 mb-3" />
                      <p className="text-gray-500">No decisions recorded yet</p>
                      <p className="text-xs text-gray-600 mt-1">
                        Preview an opportunity to generate a risk decision
                      </p>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Legend */}
          <div className="mt-4 pt-4 border-t border-gray-800 flex gap-6 text-xs text-gray-500">
            <div className="flex items-center gap-1">
              <CheckCircle size={12} className="text-green-500" />
              Allowed
            </div>
            <div className="flex items-center gap-1">
              <XCircle size={12} className="text-red-500" />
              Blocked
            </div>
            <div className="flex items-center gap-1">
              <Clock size={12} className="text-yellow-500" />
              Pending
            </div>
          </div>
        </div>
      )}

      {/* Orders Tab */}
      {activeTab === 'orders' && (
        <div className="card">
          <h3 className="text-sm font-medium text-gray-400 mb-4">Execution Orders</h3>

          {/* Table Header */}
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Time</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Symbol</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Side</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Size</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Venue</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Status</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Latency</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Order ID</th>
                </tr>
              </thead>
              <tbody>
                {/* Empty State */}
                <tr>
                  <td colSpan={8} className="py-12 text-center">
                    <div className="flex flex-col items-center">
                      <AlertCircle size={32} className="text-gray-700 mb-3" />
                      <p className="text-gray-500">No orders executed yet</p>
                      <p className="text-xs text-gray-600 mt-1">
                        Execute a trade to see order history
                      </p>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          {/* Legend */}
          <div className="mt-4 pt-4 border-t border-gray-800 flex gap-6 text-xs text-gray-500">
            <div className="flex items-center gap-1">
              <CheckCircle size={12} className="text-green-500" />
              Placed
            </div>
            <div className="flex items-center gap-1">
              <Clock size={12} className="text-yellow-500" />
              Pending
            </div>
            <div className="flex items-center gap-1">
              <XCircle size={12} className="text-red-500" />
              Failed
            </div>
          </div>
        </div>
      )}

      {/* Market Alerts Tab */}
      {activeTab === 'alerts' && (
        <div className="card">
          <h3 className="text-sm font-medium text-gray-400 mb-4">Market Alerts</h3>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-800">
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Time</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Symbol</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Type</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Metric</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Change</th>
                  <th className="text-left py-3 px-2 text-gray-500 font-medium">Venue</th>
                </tr>
              </thead>
              <tbody>
                {alerts.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-12 text-center">
                      <div className="flex flex-col items-center">
                        <Activity size={32} className="text-gray-700 mb-3" />
                        <p className="text-gray-500">No market alerts recorded</p>
                        <p className="text-xs text-gray-600 mt-1">
                          Alerts trigger on regime changes and extreme values
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  alerts.map((alert) => (
                    <tr key={alert.id} className="border-b border-gray-800/50 hover:bg-gray-800/30">
                      <td className="py-2 px-2 font-mono text-xs text-gray-400">
                        {new Date(alert.ts).toLocaleString()}
                      </td>
                      <td className="py-2 px-2 font-medium">{alert.symbol}</td>
                      <td className="py-2 px-2">
                        <span className={`px-2 py-0.5 rounded text-xs ${
                          alert.alert_type === 'regime_change'
                            ? 'bg-blue-900/30 text-blue-400'
                            : alert.alert_type === 'extreme'
                            ? 'bg-red-900/30 text-red-400'
                            : 'bg-gray-800 text-gray-400'
                        }`}>
                          {alert.alert_type}
                        </span>
                      </td>
                      <td className="py-2 px-2 text-gray-300">{alert.metric}</td>
                      <td className="py-2 px-2 font-mono text-xs">
                        {alert.previous_value && (
                          <span className="text-gray-500">{alert.previous_value}</span>
                        )}
                        {alert.previous_value && ' → '}
                        <span className="text-white">{alert.new_value}</span>
                      </td>
                      <td className="py-2 px-2 text-gray-500 uppercase text-xs">{alert.venue}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Legend */}
          <div className="mt-4 pt-4 border-t border-gray-800 flex gap-6 text-xs text-gray-500">
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded bg-blue-500"></span>
              Regime Change
            </div>
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded bg-red-500"></span>
              Extreme Value
            </div>
            <div className="flex items-center gap-1">
              <span className="w-2 h-2 rounded bg-yellow-500"></span>
              Threshold
            </div>
          </div>
        </div>
      )}

      <div className="card bg-gray-900/30 text-sm text-gray-400">
        <h4 className="font-medium text-gray-300 mb-2">Audit Trail</h4>
        <p>
          Every risk decision and execution order is logged with full context.
          Use this page to review past activity, debug issues, and verify
          that policies are being correctly enforced.
        </p>
      </div>
    </div>
  )
}
