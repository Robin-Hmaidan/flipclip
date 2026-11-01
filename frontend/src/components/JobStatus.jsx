import ErrorNotice from './Notice.jsx'

const LABELS = {
  queued: 'Waiting to start…',
  downloading: 'Downloading from YouTube…',
}

export function ProgressBar({ label, value }) {
  return (
    <div className="progress">
      <div className="progress-label">
        <span>{label}</span>
        <span className="progress-value">{value}%</span>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-label={label}
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="progress-fill" style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

// Shown until the job has a video: download progress, or why it failed.
export default function JobStatus({ job, onRetry, onStartOver }) {
  if (job.status === 'failed') {
    return (
      <ErrorNotice title="We couldn't get that video" message={job.error || 'Something went wrong.'} onRetry={onRetry}>
        <button type="button" className="secondary" onClick={onStartOver}>
          Choose another video
        </button>
      </ErrorNotice>
    )
  }
  return (
    <div className="card">
      <ProgressBar label={LABELS[job.status] ?? 'Working…'} value={job.progress} />
    </div>
  )
}
