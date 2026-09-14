export function TradePlanSkeleton() {
  return (
    <section className="card bg-gray-900/20 border-gray-800">
      <h3 className="text-xs font-bold text-gray-500 uppercase tracking-widest mb-3">Proposed Trade Plan</h3>
      <div className="space-y-3">
        <div className="flex justify-between items-center p-2 bg-gray-900 rounded border border-gray-800">
          <span className="text-xs text-gray-500">ENTRY</span>
          <span className="font-mono font-bold">$---.---</span>
        </div>
        <div className="flex justify-between items-center p-2 bg-gray-900 rounded border border-gray-800">
          <span className="text-xs text-red-900 font-bold">STOP LOSS</span>
          <span className="font-mono font-bold text-red-900">$---.---</span>
        </div>
        <div className="flex justify-between items-center p-2 bg-gray-900 rounded border border-gray-800">
          <span className="text-xs text-green-900 font-bold">TAKE PROFIT</span>
          <span className="font-mono font-bold text-green-900">$---.---</span>
        </div>
      </div>
      <p className="mt-3 text-[10px] text-gray-600 text-center italic">
        Live market quotes required to finalize levels.
      </p>
    </section>
  )
}
