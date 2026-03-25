import { MessageSquare, Mic, BookOpen, AlertCircle, Send } from 'lucide-react'

export function Copilot() {
  return (
    <div className="space-y-6 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">AI Copilot</h2>
        <span className="text-xs bg-yellow-900/50 text-yellow-400 px-2 py-1 rounded">
          COMING IN PHASE 4
        </span>
      </div>

      {/* Mode Selector */}
      <div className="flex gap-2">
        <button className="px-4 py-2 bg-blue-600 text-white rounded text-sm flex items-center gap-2">
          <MessageSquare size={14} />
          Chat
        </button>
        <button className="px-4 py-2 bg-gray-800 text-gray-400 rounded text-sm flex items-center gap-2" disabled>
          <Mic size={14} />
          Voice
          <span className="text-[10px] bg-gray-700 px-1.5 py-0.5 rounded">SOON</span>
        </button>
      </div>

      {/* Chat Area */}
      <div className="flex-1 card bg-gray-900/30 flex flex-col min-h-[400px]">
        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto p-4 flex flex-col items-center justify-center text-center">
          <AlertCircle size={36} className="text-gray-700 mb-3" />
          <p className="text-gray-400 text-sm font-medium">Copilot not available</p>
          <p className="text-gray-600 text-xs mt-2 max-w-xs">
            The AI Copilot backend has not been implemented yet. This feature is
            planned for Phase 4 and requires an LLM endpoint, Qdrant vector store,
            and the Sources Library to be populated first.
          </p>
        </div>

        {/* Input Area */}
        <div className="border-t border-gray-800 p-4">
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Ask about opportunities, risk, or your sources..."
              className="input flex-1"
              disabled
            />
            <button
              className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              disabled
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Citations Panel */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
          <BookOpen size={14} />
          Citations & Sources
        </h3>
        <div className="bg-gray-900/50 border border-gray-800 border-dashed rounded-lg p-4 text-center">
          <p className="text-xs text-gray-600">
            When the copilot references your documents or live data,
            citations will appear here for verification.
          </p>
        </div>
      </div>

      <div className="card bg-gray-900/30 text-sm text-gray-400">
        <h4 className="font-medium text-gray-300 mb-2">Phase 4: AI Copilot</h4>
        <p>
          A context-aware AI assistant that understands your trading context.
          It can analyze opportunities, explain signals, query your knowledge base,
          and help you make informed decisions. Voice interface planned for Phase 5.
        </p>
      </div>
    </div>
  )
}
