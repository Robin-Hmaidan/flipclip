import { formatTime } from '../format.js'

export default function Preview({ job, videoRef, onSeeking }) {
  return (
    <div className="preview">
      {/* Keyed by id so a new job always loads a fresh source. */}
      <video
        key={job.id}
        ref={videoRef}
        src={`/api/jobs/${job.id}/video`}
        controls
        playsInline
        preload="metadata"
        onSeeking={onSeeking}
      />
      <dl className="meta">
        <div>
          <dt>Duration</dt>
          <dd>{formatTime(job.duration)}</dd>
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
