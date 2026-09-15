import styles from './PageLoading.module.css'

/** Shown inside the frame while a page's code downloads; the sidebar and header stay usable. */
export function PageLoading() {
  return (
    <div className={styles.loading} role="status" aria-live="polite">
      Loading page…
    </div>
  )
}
