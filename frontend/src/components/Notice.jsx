// An error the user can act on: what happened in plain words, then "Try again" and/or another way out.
export default function ErrorNotice({ title = 'Something went wrong', message, onRetry, retryLabel = 'Try again', children }) {
  return (
    <div className="notice notice--error" role="alert">
      <span className="notice-icon" aria-hidden="true">
        !
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
