import { useRef } from 'react'
import { formatTime } from '../format.js'

// The source video. Once there are clips it becomes "Before", next to the vertical "After" clip,
// or next to a placeholder that says how to get one. Phones stack the two (see .compare in CSS).
export default function Preview({ job, videoRef, onSeeking, vertical, showPlaceholder, onPlayRange, onCloseVertical }) {
  const verticalRef = useRef(null)
  const paired = Boolean(vertical) || showPlaceholder

  function playBoth() {
    const v = verticalRef.current
    if (!v) return
    onPlayRange(vertical.clip)
    v.currentTime = 0
    v.muted = true // same soundtrack as the original; two copies would echo
    v.play().catch(() => {})
  }

  const range = vertical && `${formatTime(vertical.clip.start)}–${formatTime(vertical.clip.end)}`

  return (
    <section className="card preview" aria-labelledby="preview-title">
      <div className="section-head">
        <h2 id="preview-title">{vertical ? `Clip ${vertical.clip.index + 1}: before and after` : 'Your video'}</h2>
        <p className="section-meta">
          {formatTime(job.duration)} · {job.width} × {job.height}
        </p>
      </div>

      <div className={paired ? 'compare' : undefined}>
        <figure className="compare-original">
          {paired && (
            <figcaption>
              <span className="badge">Before</span> Original 16:9{range && ` · ${range}`}
            </figcaption>
          )}
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
        </figure>

        {vertical && (
          <figure className="compare-vertical">
            <figcaption>
              <span className="badge badge--accent">After</span> Vertical 9:16
            </figcaption>
            <video key={vertical.url} ref={verticalRef} src={vertical.url} controls playsInline preload="metadata" />
          </figure>
        )}

        {!vertical && showPlaceholder && (
          <div className="compare-vertical compare-empty">
            <span className="badge badge--accent">After</span>
            <div className="compare-empty-frame" aria-hidden="true" />
            <p>
              Your vertical clip shows up here. Tap <strong>Make vertical</strong> on any clip below.
            </p>
          </div>
        )}
      </div>

      {vertical && (
        <div className="button-row">
          <button type="button" onClick={playBoth}>
            Play both
          </button>
          <a className="button secondary" href={vertical.downloadUrl} download>
            Download
          </a>
          <button type="button" className="secondary" onClick={onCloseVertical}>
            Close
          </button>
        </div>
      )}
    </section>
  )
}
