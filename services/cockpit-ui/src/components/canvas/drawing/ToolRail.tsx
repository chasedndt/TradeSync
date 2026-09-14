import { useState, type ReactNode } from 'react'
import {
  ArrowRightFromLine,
  ChartNoAxesGantt,
  Eye,
  EyeOff,
  Lock,
  LockOpen,
  Minus,
  MousePointer2,
  MoveDiagonal2,
  MoveUpRight,
  Pencil,
  RectangleHorizontal,
  Ruler,
  SeparatorVertical,
  Slash,
  Trash2,
  Type,
  type LucideIcon,
} from 'lucide-react'
import { ClearConfirm } from './ClearConfirm'
import type { ToolId } from './types'
import styles from './ToolRail.module.css'

const TOOLS: ReadonlyArray<{ id: ToolId; icon: LucideIcon; label: string }> = [
  { id: 'cursor', icon: MousePointer2, label: 'Cursor: select and move drawings' },
  { id: 'trendline', icon: Slash, label: 'Trend line' },
  { id: 'ray', icon: MoveUpRight, label: 'Ray' },
  { id: 'extended_line', icon: MoveDiagonal2, label: 'Extended line' },
  { id: 'horizontal', icon: Minus, label: 'Horizontal line' },
  { id: 'horizontal_ray', icon: ArrowRightFromLine, label: 'Horizontal ray' },
  { id: 'vertical', icon: SeparatorVertical, label: 'Vertical line' },
  { id: 'rectangle', icon: RectangleHorizontal, label: 'Rectangle' },
  { id: 'fib_retracement', icon: ChartNoAxesGantt, label: 'Fib retracement' },
  { id: 'measure', icon: Ruler, label: 'Measure: price, bars and time (not saved)' },
  { id: 'pencil', icon: Pencil, label: 'Pencil (stays on until Esc)' },
  { id: 'text', icon: Type, label: 'Text' },
]

interface Props {
  tool: ToolId
  onTool: (tool: ToolId) => void
  hidden: boolean
  onToggleHidden: () => void
  locked: boolean
  onToggleLocked: () => void
  /** Drawings for this symbol, across every interval. */
  count: number
  symbol: string
  onClearAll: () => void
}

/** The drawing tools, beside the chart as on TradingView, with show, lock and clear below them. */
export function ToolRail({ tool, onTool, hidden, onToggleHidden, locked, onToggleLocked, count, symbol, onClearAll }: Props) {
  const [confirming, setConfirming] = useState(false)

  return (
    <div className={styles.rail} role="toolbar" aria-label="Drawing tools" aria-orientation="vertical">
      {TOOLS.map(({ id, icon: Icon, label }) => (
        <RailButton key={id} label={label} active={tool === id} onClick={() => onTool(id)}>
          <Icon size={17} strokeWidth={1.75} aria-hidden />
        </RailButton>
      ))}
      <span className={styles.divider} />
      <RailButton label={hidden ? 'Show drawings' : 'Hide drawings'} active={hidden} onClick={onToggleHidden}>
        {hidden ? <EyeOff size={17} strokeWidth={1.75} aria-hidden /> : <Eye size={17} strokeWidth={1.75} aria-hidden />}
      </RailButton>
      <RailButton label={locked ? 'Unlock drawings' : 'Lock drawings'} active={locked} onClick={onToggleLocked}>
        {locked ? <Lock size={17} strokeWidth={1.75} aria-hidden /> : <LockOpen size={17} strokeWidth={1.75} aria-hidden />}
      </RailButton>
      <div className={styles.clear}>
        <RailButton
          label={locked ? 'Unlock drawings to delete them' : `Delete all drawings for ${symbol}`}
          disabled={count === 0 || locked}
          onClick={() => setConfirming(true)}
        >
          <Trash2 size={17} strokeWidth={1.75} aria-hidden />
        </RailButton>
        {confirming && (
          <ClearConfirm
            symbol={symbol}
            count={count}
            onConfirm={() => {
              setConfirming(false)
              onClearAll()
            }}
            onCancel={() => setConfirming(false)}
          />
        )}
      </div>
    </div>
  )
}

interface RailButtonProps {
  label: string
  active?: boolean
  disabled?: boolean
  onClick: () => void
  children: ReactNode
}

function RailButton({ label, active = false, disabled = false, onClick, children }: RailButtonProps) {
  return (
    <button
      type="button"
      className={active ? `${styles.button} ${styles.active}` : styles.button}
      aria-label={label}
      aria-pressed={active}
      data-tip={label}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  )
}
