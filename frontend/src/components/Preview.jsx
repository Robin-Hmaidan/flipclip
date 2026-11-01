import { useRef } from 'react'
import { clipNumber, formatTimecode } from '../format.js'

// The source video, and once there are clips, a phone showing the vertical result next to it
// (or saying how to get one). Phones stack the two, and skip the empty phone (see .viewer in CSS).
export default function Preview({
  job,
  videoRef,
  onSeeking,
  onPause,
  onSourceError,
  vertical,
  showPhone,
  onPlayRange,
  onCloseVertical,
}) {
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
    <section className={`viewer${showPhone ? ' viewer--paired' : ''}`} aria-label="Preview">
      <figure className="source">
        <figcaption className="panel-head">
          <span className="label">Source</span>
          <span className="mono meta">
            {formatTimecode(job.duration)} · {job.width}×{job.height}
          </span>
        </figcaption>
        {/* Keyed by id so a new job always loads a fresh source. */}
        <video
          key={job.id}
          ref={videoRef}
          src={`/api/jobs/${job.id}/video`}
          controls
          playsInline
          preload="metadata"
          onSeeking={onSeeking}
          onPause={onPause}
          onError={onSourceError}
        />
      </figure>

      {showPhone && (
        <figure className={`vertical${vertical ? '' : ' vertical--empty'}`}>
          <figcaption className="panel-head">
            <span className="label">Vertical</span>
            <span className="mono meta">{vertical ? `Clip ${clipNumber(vertical.clip.index)} · 9:16` : '9:16'}</span>
          </figcaption>
          <div className="phone">
            <div className="phone-screen">
              {vertical ? (
                <video key={vertical.url} ref={verticalRef} src={vertical.url} controls playsInline preload="metadata" />
              ) : (
                <p className="phone-empty">
                  Choose <strong>Make vertical</strong> on a clip to see it here.
                </p>
              )}
            </div>
          </div>
          {vertical && (
            <div className="button-row">
              <button type="button" onClick={playBoth}>
                Play both
              </button>
              <a className="button secondary" href={vertical.downloadUrl} download>
                Download clip
              </a>
              <button type="button" className="secondary" onClick={onCloseVertical}>
                Close
              </button>
            </div>
          )}
        </figure>
      )}
    </section>
  )
}
