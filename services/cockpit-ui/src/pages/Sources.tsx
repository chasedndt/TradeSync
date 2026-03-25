import { FileText, Link, Upload, Search, Tag, AlertCircle } from 'lucide-react'

export function Sources() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold">Sources Library</h2>
        <span className="text-xs bg-yellow-900/50 text-yellow-400 px-2 py-1 rounded">
          COMING IN PHASE 4
        </span>
      </div>

      {/* Upload Zone — disabled, Phase 4 not implemented */}
      <div className="card border-dashed border-2 border-gray-800 opacity-40 pointer-events-none select-none">
        <div className="flex flex-col items-center justify-center py-8 text-center">
          <Upload size={32} className="text-gray-700 mb-3" />
          <p className="text-gray-600 mb-1">Drag & drop files here</p>
          <p className="text-xs text-gray-700">
            Not available — Phase 4 feature
          </p>
        </div>
      </div>

      {/* Source Types Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 opacity-40 pointer-events-none select-none">
        <div className="card bg-gray-900/50">
          <div className="flex items-center gap-3 mb-3">
            <FileText size={20} className="text-blue-500" />
            <h3 className="font-medium">Documents</h3>
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Research papers, trading plans, and strategy documents for RAG retrieval.
          </p>
          <div className="text-sm text-gray-600 italic">0 documents indexed</div>
        </div>

        <div className="card bg-gray-900/50">
          <div className="flex items-center gap-3 mb-3">
            <Link size={20} className="text-green-500" />
            <h3 className="font-medium">Web Links</h3>
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Bookmarked analysis, TradingView ideas, and reference articles.
          </p>
          <div className="text-sm text-gray-600 italic">0 links saved</div>
        </div>

        <div className="card bg-gray-900/50">
          <div className="flex items-center gap-3 mb-3">
            <Tag size={20} className="text-purple-500" />
            <h3 className="font-medium">Tags & Categories</h3>
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Organize sources by symbol, strategy, timeframe, or custom tags.
          </p>
          <div className="text-sm text-gray-600 italic">No tags created</div>
        </div>
      </div>

      {/* Search */}
      <div className="card">
        <h3 className="text-sm font-medium text-gray-400 mb-3 flex items-center gap-2">
          <Search size={14} />
          Semantic Search
        </h3>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" size={16} />
          <input
            type="text"
            placeholder="Search your knowledge base..."
            className="input w-full pl-10"
            disabled
          />
        </div>
        <div className="mt-4 bg-gray-900/50 border border-gray-800 border-dashed rounded-lg p-6 text-center">
          <AlertCircle size={24} className="text-gray-700 mx-auto mb-2" />
          <p className="text-xs text-gray-600">
            Qdrant vector store not configured for RAG retrieval
          </p>
        </div>
      </div>

      <div className="card bg-gray-900/30 text-sm text-gray-400">
        <h4 className="font-medium text-gray-300 mb-2">Phase 4: RAG Knowledge Base</h4>
        <p>
          This page will allow you to upload and manage your trading research library.
          Documents are chunked, embedded, and stored in Qdrant for semantic retrieval
          by the AI Copilot during analysis and trade thesis generation.
        </p>
      </div>
    </div>
  )
}
