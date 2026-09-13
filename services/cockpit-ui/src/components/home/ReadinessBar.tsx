import { NavLink } from 'react-router-dom'
import styles from './Home.module.css'

export interface ReadinessChip {
  label: string
  value: string
  detail: string
  tone: 'good' | 'warn' | 'bad' | 'dim'
  to: string
  icon: React.ReactNode
}

/** Readiness in one thin line: label, state, one detail, each linking to what explains it. */
export function ReadinessBar({ chips }: { chips: ReadinessChip[] }) {
  return (
    <section className={`panel ${styles.readiness}`} aria-label="System readiness">
      {chips.map((c) => (
        <NavLink key={c.label} to={c.to} className={styles.chip} title={`Inspect ${c.label.toLowerCase()}`}>
          <span className={`tone-${c.tone}`}>{c.icon}</span>
          <span className={styles.chipLabel}>{c.label}</span>
          <span className={`${styles.chipValue} tone-${c.tone}`}>{c.value}</span>
          <span className={styles.chipDetail}>{c.detail}</span>
        </NavLink>
      ))}
    </section>
  )
}
