import { useEffect, useState } from 'react'
import { getClips } from '../api.js'
import ClipCard from './ClipCard.jsx'
import ExportPanel from './ExportPanel.jsx'

export default function ClipList({
  jobId,
  duration,
  limits,
  playingIndex,
  showingIndex,
  onPlay,
  onShowVertical,
  onRendered,
  onEditOpen,
  onEdited,
}) {
  const [clips, setClips] = useState(null)
  const [error, setError] = useState(null)
  // Bumped when an export starts, so every card picks up the renders it queued.
  const [syncKey, setSyncKey] = useState(0)
  // Bumped after an edit: the server dropped the zip, so the export panel re-reads its state.
  const [editKey, setEditKey] = useState(0)

  function handleEdited(saved) {
    setClips((list) => list.map((c) => (c.index === saved.index ? saved : c)))
    setEditKey((k) => k + 1)
    onEdited(saved)
  }

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
      <div className="clips-header">
        <h2>
          {clips.length} {clips.length === 1 ? 'clip' : 'clips'}
        </h2>
        <ExportPanel jobId={jobId} refreshKey={editKey} onStarted={() => setSyncKey((k) => k + 1)} />
      </div>
      <ol className="clip-grid">
        {clips.map((clip) => (
          <ClipCard
            // New bounds remount the card: its render was dropped, so its state starts over.
            key={`${clip.index}:${clip.start}:${clip.end}`}
            jobId={jobId}
            clip={clip}
            duration={duration}
            limits={limits}
            playing={clip.index === playingIndex}
            showing={clip.index === showingIndex}
            syncKey={syncKey}
            onPlay={onPlay}
            onShowVertical={onShowVertical}
            onRendered={onRendered}
            onEditOpen={onEditOpen}
            onEdited={handleEdited}
          />
        ))}
      </ol>
    </section>
  )
}
