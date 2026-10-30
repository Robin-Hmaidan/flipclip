import { useEffect, useState } from 'react'
import { getClips } from '../api.js'
import { formatTime } from '../format.js'

export default function ClipList({ jobId, activeIndex, onSelect }) {
  const [clips, setClips] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    getClips(jobId)
      .then((list) => !cancelled && setClips(list))
      .catch((err) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [jobId])

  if (error) return <p className="message message--error">{error}</p>
  if (!clips) return <p className="message">Loading clips…</p>

  return (
    <section className="clips">
      <h2>
        {clips.length} {clips.length === 1 ? 'clip' : 'clips'}
      </h2>
      <ol className="clip-grid">
        {clips.map((clip) => (
          <li key={clip.index}>
            <button
              type="button"
              className={`clip${clip.index === activeIndex ? ' clip--active' : ''}`}
              aria-pressed={clip.index === activeIndex}
              onClick={() => onSelect(clip)}
            >
              <img src={clip.thumbnail_url} alt="" loading="lazy" width="320" height="180" />
              <span className="clip-time">
                {formatTime(clip.start)}–{formatTime(clip.end)}
              </span>
              <span className="clip-duration">{formatTime(clip.duration)}</span>
            </button>
          </li>
        ))}
      </ol>
    </section>
  )
}
