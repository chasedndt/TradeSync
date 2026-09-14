import { Component, type ErrorInfo, type ReactNode } from 'react'
import styles from './SectionBoundary.module.css'

interface Props {
  name: string
  /** A change (the selected market) clears a previous failure and renders again. */
  resetKey?: string
  children: ReactNode
}

interface State {
  error: Error | null
}

/** Keeps one section's rendering failure inside that section and names it; the rest of the page stays usable. */
export class SectionBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(`[Regime Lab] ${this.props.name} failed to render`, error, info.componentStack)
  }

  componentDidUpdate(previous: Props) {
    if (this.state.error && previous.resetKey !== this.props.resetKey) this.setState({ error: null })
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <section className={`panel ${styles.failed}`} role="alert">
        <strong>{this.props.name} could not be shown.</strong>
        <span>{this.state.error.message}</span>
        <button type="button" className="chip" onClick={() => this.setState({ error: null })}>Try again</button>
      </section>
    )
  }
}
