import { DirectionBadge } from '../DirectionBadge'
import type { Position } from '../../api/types'

export function PositionsTable({ positions }: { positions: Position[] }) {
  return (
    <div className="card overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-400 border-b border-gray-700">
            <th className="pb-2">Symbol</th>
            <th className="pb-2">Venue</th>
            <th className="pb-2">Side</th>
            <th className="pb-2">Size</th>
            <th className="pb-2">Entry</th>
            <th className="pb-2">Mark</th>
            <th className="pb-2">PnL</th>
            <th className="pb-2">Leverage</th>
          </tr>
        </thead>
        <tbody>
          {positions.map((pos, idx) => (
            <tr key={idx} className="border-b border-gray-800">
              <td className="py-2 font-medium">{pos.symbol}</td>
              <td className="py-2 text-gray-400 capitalize">{pos.venue}</td>
              <td className="py-2">
                <DirectionBadge direction={pos.side} />
              </td>
              <td className="py-2">${pos.size_usd.toFixed(2)}</td>
              <td className="py-2">${pos.entry_price.toFixed(4)}</td>
              <td className="py-2">${pos.mark_price.toFixed(4)}</td>
              <td className={`py-2 ${pos.pnl_usd >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                ${pos.pnl_usd.toFixed(2)}
              </td>
              <td className="py-2">{pos.leverage}x</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
