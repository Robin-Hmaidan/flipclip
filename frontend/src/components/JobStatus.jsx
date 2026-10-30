const LABELS = {
  queued: 'Waiting to start…',
  downloading: 'Downloading from YouTube…',
}

export function ProgressBar({ label, value }) {
  return (
    <div className="progress">
      <div className="progress-label">
        <span>{label}</span>
        <span>{value}%</span>
      </div>
      <div className="progress-track" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
        <div className="progress-fill" style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

// Shown until the job has a video: download progress, or why it failed.
export default function JobStatus({ job }) {
  if (job.status === 'failed') {
    return <p className="message message--error">{job.error || 'Something went wrong.'}</p>
  }
  return <ProgressBar label={LABELS[job.status] ?? job.status} value={job.progress} />
}
