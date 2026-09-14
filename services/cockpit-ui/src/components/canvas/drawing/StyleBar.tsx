import { Lock, Trash2 } from 'lucide-react'
import { KIND_NAMES } from './tools'
import type { ChartShape, DrawingStyle } from './types'
import styles from './StyleBar.module.css'

const SWATCHES = ['#e3b23c', '#4196ff', '#3fb27f', '#e0574a', '#a968ff', '#dce5ee'] as const
const WIDTHS = [1, 2, 3, 4] as const

interface Props {
  shape: ChartShape
  /** The interval on screen; a drawing made on another says which. */
  interval: string
  locked: boolean
  onStyle: (style: DrawingStyle) => void
  onDelete: () => void
}

/** Colour, width, line style and delete for the selected drawing. New drawings take the last style chosen. */
export function StyleBar({ shape, interval, locked, onStyle, onDelete }: Props) {
  const { style } = shape
  const isText = shape.kind === 'text' || shape.kind === 'note'
  const set = (changes: Partial<DrawingStyle>) => onStyle({ ...style, ...changes })
  const name = [
    KIND_NAMES[shape.kind],
    shape.version ? `v${shape.version}` : null,
    shape.interval && shape.interval !== interval ? `drawn on ${shape.interval}` : null,
  ].filter(Boolean).join(' · ')

  return (
    <div className={styles.bar} role="toolbar" aria-label="Drawing style">
      <span className={styles.name}>{name}</span>
      <div className={styles.group} role="radiogroup" aria-label="Colour">
        {SWATCHES.map((colour) => (
          <button
            key={colour}
            type="button"
            role="radio"
            aria-checked={style.colour === colour}
            aria-label={`Colour ${colour}`}
            className={style.colour === colour ? `${styles.swatch} ${styles.chosen}` : styles.swatch}
            style={{ background: colour }}
            disabled={locked}
            onClick={() => set({ colour })}
          />
        ))}
      </div>
      {!isText && (
        <>
          <div className={styles.group} role="radiogroup" aria-label="Line width">
            {WIDTHS.map((width) => (
              <button
                key={width}
                type="button"
                role="radio"
                aria-checked={style.width === width}
                aria-label={`Width ${width}`}
                className={style.width === width ? `${styles.option} ${styles.chosen}` : styles.option}
                disabled={locked}
                onClick={() => set({ width })}
              >
                <span className={styles.widthSample} style={{ height: width }} />
              </button>
            ))}
          </div>
          <button
            type="button"
            className={styles.option}
            aria-pressed={style.dashed}
            aria-label={style.dashed ? 'Dashed line; switch to solid' : 'Solid line; switch to dashed'}
            title={style.dashed ? 'Dashed' : 'Solid'}
            disabled={locked}
            onClick={() => set({ dashed: !style.dashed })}
          >
            <span className={style.dashed ? styles.dashedSample : styles.solidSample} />
          </button>
        </>
      )}
      {locked && <Lock className={styles.lock} size={14} strokeWidth={1.75} aria-label="Drawings are locked" />}
      <button
        type="button"
        className={`${styles.option} ${styles.delete}`}
        aria-label="Delete drawing"
        title={locked ? 'Unlock drawings to delete' : 'Delete (Del)'}
        disabled={locked}
        onClick={onDelete}
      >
        <Trash2 size={15} strokeWidth={1.75} aria-hidden />
      </button>
    </div>
  )
}
