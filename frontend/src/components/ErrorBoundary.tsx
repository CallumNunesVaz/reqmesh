import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          height: '100vh',
          padding: '2rem',
          fontFamily: 'Inter, system-ui, sans-serif',
          color: 'var(--c-text, #1e293b)',
          background: 'var(--c-bg, #f8fafc)',
        }}>
          <h1 style={{ fontSize: '1.5rem', fontWeight: 600, marginBottom: '0.5rem' }}>
            Something went wrong
          </h1>
          <p style={{ color: 'var(--c-muted, #64748b)', marginBottom: '1.5rem', maxWidth: '28rem', textAlign: 'center' }}>
            An unexpected error occurred. Please reload the page to continue.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '0.5rem 1.25rem',
              fontSize: '0.875rem',
              fontWeight: 500,
              border: 'none',
              borderRadius: '0.375rem',
              cursor: 'pointer',
              background: 'var(--c-accent, #2094f3)',
              color: '#fff',
            }}
          >
            Reload
          </button>
          <details style={{ marginTop: '2rem', maxWidth: '36rem', width: '100%' }}>
            <summary style={{ cursor: 'pointer', color: 'var(--c-muted, #64748b)', fontSize: '0.8125rem' }}>
              Error details
            </summary>
            <pre style={{
              marginTop: '0.5rem',
              padding: '1rem',
              fontSize: '0.75rem',
              overflow: 'auto',
              background: 'var(--c-surface, #fff)',
              border: '1px solid var(--c-border, #e2e8f0)',
              borderRadius: '0.375rem',
              whiteSpace: 'pre-wrap',
            }}>
              {this.state.error.message}
              {'\n\n'}
              {this.state.error.stack}
            </pre>
          </details>
        </div>
      );
    }

    return this.props.children;
  }
}
