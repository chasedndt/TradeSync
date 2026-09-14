import { OpportunityList } from '../components/opportunities/OpportunityList'
import styles from './Opportunities.module.css'

export function Opportunities() {
  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h2 className={styles.title}>Market Opportunities</h2>
      </div>
      <OpportunityList />
    </div>
  )
}
