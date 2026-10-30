import { useRef } from 'react'
import { formatTime } from '../format.js'

// The source video, plus the rendered vertical clip beside it when one is open.
export default function Preview({ job, videoRef, onSeeking, vertical, onPlayRange, onCloseVertical }) {
  const verticalRef = useRef(null)

  function playBoth() {
    const v = verticalRef.current
    if (!v) return
    onPlayRange(vertical.clip)
    v.currentTime = 0
    v.muted = true // same soundtrack as the original; two copies would echo
    v.play().catch(() => {})
  }

  return (
    <div className="preview">
      <div className={vertical ? 'compare' : undefined}>
        <figure className="compare-original">
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
          {vertical && <figcaption>Original</figcaption>}
        </figure>
        {vertical && (
          <figure className="compare-vertical">
            <video key={vertical.url} ref={verticalRef} src={vertical.url} controls playsInline preload="metadata" />
            <figcaption>
              Vertical · {formatTime(vertical.clip.start)}–{formatTime(vertical.clip.end)}
            </figcaption>
          </figure>
        )}
      </div>

      {vertical ? (
        <div className="compare-actions">
          <button type="button" className="small" onClick={playBoth}>
            Play side by side
          </button>
          <button type="button" className="small secondary" onClick={onCloseVertical}>
            Close vertical
          </button>
        </div>
      ) : (
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
      )}
    </div>
  )
}
