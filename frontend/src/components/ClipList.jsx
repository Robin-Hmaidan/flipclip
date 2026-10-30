import { useEffect, useState } from 'react'
import { getClips } from '../api.js'
import ClipCard from './ClipCard.jsx'

export default function ClipList({ jobId, playingIndex, showingIndex, onPlay, onShowVertical, onRendered }) {
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
          <ClipCard
            key={clip.index}
            jobId={jobId}
            clip={clip}
            playing={clip.index === playingIndex}
            showing={clip.index === showingIndex}
            onPlay={onPlay}
            onShowVertical={onShowVertical}
            onRendered={onRendered}
          />
        ))}
      </ol>
    </section>
  )
}
