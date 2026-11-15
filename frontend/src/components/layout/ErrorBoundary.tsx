import { Component, type ErrorInfo, type ReactNode } from 'react'

interface State { error: Error | null }

// A failure in one view must not leave a blank page: say what happened and offer a way back.
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('CascadeLens view failed', error, info.componentStack)
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    return (
      <section className="app-error" role="alert" aria-labelledby="app-error-title">
        <h1 id="app-error-title">This view stopped working</h1>
        <p>CascadeLens hit an error it could not recover from in this view. No data was changed. Reloading starts the app again from the opening screen.</p>
        <p className="app-error-detail">Error: {error.message || 'unknown error'}</p>
        <button className="primary" onClick={() => window.location.reload()}>Reload CascadeLens</button>
      </section>
    )
  }
}
