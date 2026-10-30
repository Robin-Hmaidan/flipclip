const LABELS = {
  queued: 'Waiting to start…',
  downloading: 'Downloading from YouTube…',
  ready: 'Ready',
  failed: 'Failed',
}

function formatDuration(seconds) {
  const s = Math.round(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const rest = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${rest}` : `${m}:${rest}`
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

export default function JobStatus({ job }) {
  if (job.status === 'failed') {
    return <p className="message message--error">{job.error || 'Something went wrong.'}</p>
  }
  if (job.status !== 'ready') {
    return <ProgressBar label={LABELS[job.status] ?? job.status} value={job.progress} />
  }
  return (
    <div className="preview">
      {/* Keyed by id so a new job always loads a fresh source. */}
      <video key={job.id} src={`/api/jobs/${job.id}/video`} controls playsInline preload="metadata" />
      <dl className="meta">
        <div>
          <dt>Duration</dt>
          <dd>{formatDuration(job.duration)}</dd>
        </div>
        <div>
          <dt>Resolution</dt>
          <dd>
            {job.width} × {job.height}
          </dd>
        </div>
      </dl>
    </div>
  )
}
