import { useSearchParams } from 'react-router-dom'
import { LearningView } from '../components/learning/LearningView'
import { OpportunityList } from '../components/opportunities/OpportunityList'
import styles from './Opportunities.module.css'

const VIEWS = [
  { id: 'list', label: 'Opportunities' },
  { id: 'learning', label: 'Learning' },
] as const

/** Opportunities, and what their measured outcomes have taught the scorer, as two views of one page. */
export function Opportunities() {
  const [params, setParams] = useSearchParams()
  const view = params.get('view') === 'learning' ? 'learning' : 'list'

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>Market Opportunities</h2>
        <div className={styles.tabs} role="tablist" aria-label="Opportunities views">
          {VIEWS.map((item) => (
            <button
              key={item.id}
              id={`opportunities-tab-${item.id}`}
              type="button"
              role="tab"
              aria-selected={view === item.id}
              aria-controls="opportunities-panel"
              className={view === item.id ? 'chip chip--active' : 'chip'}
              onClick={() => setParams(item.id === 'learning' ? { view: 'learning' } : {}, { replace: true })}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>
      <div id="opportunities-panel" role="tabpanel" aria-labelledby={`opportunities-tab-${view}`}>
        {view === 'learning' ? <LearningView /> : <OpportunityList />}
      </div>
    </div>
  )
}
