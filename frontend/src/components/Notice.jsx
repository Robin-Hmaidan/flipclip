// An error the user can act on: what happened in plain words, then "Try again" and/or another way out.
// tone="busy" is for the server being full: not the user's fault, so calmer colours and a clock.
export default function ErrorNotice({
  title = 'Something went wrong',
  message,
  onRetry,
  retryLabel = 'Try again',
  tone = 'error',
  children,
}) {
  return (
    <div className={`notice notice--${tone}`} role={tone === 'busy' ? 'status' : 'alert'}>
      <span className="notice-icon" aria-hidden="true">
        {tone === 'busy' ? <ClockIcon /> : '!'}
      </span>
      <div className="notice-body">
        <p className="notice-title">{title}</p>
        {message && <p className="notice-message">{message}</p>}
        {(onRetry || children) && (
          <div className="notice-actions">
            {onRetry && (
              <button type="button" onClick={onRetry}>
                {retryLabel}
              </button>
            )}
            {children}
          </div>
        )}
      </div>
    </div>
  )
}

function ClockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="8" cy="8" r="6" />
      <path d="M8 4.5V8l2.5 1.5" />
    </svg>
  )
}
