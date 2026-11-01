// An error the user can act on: what happened in plain words, then "Try again" and/or another way out.
// tone="busy" is for the server being full: not the user's fault, so a neutral tone and a clock.
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
        {tone === 'busy' ? <ClockIcon /> : <AlertIcon />}
      </span>
      <div className="notice-body">
        <p className="notice-title">{title}</p>
        {message && <p className="notice-message">{message}</p>}
        {(onRetry || children) && (
          <div className="button-row">
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
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="8" cy="8" r="6.25" />
      <path d="M8 4.5V8l2.5 1.5" />
    </svg>
  )
}

function AlertIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="8" cy="8" r="6.25" />
      <path d="M8 4.5v4M8 11v.01" />
    </svg>
  )
}
