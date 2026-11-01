import { useEffect, useState } from 'react'
import { getClips } from '../api.js'
import ClipCard from './ClipCard.jsx'
import ExportPanel from './ExportPanel.jsx'
import ErrorNotice from './Notice.jsx'

// Grey stand-ins with the cards' shape, so the page doesn't jump when the clips arrive.
export function ClipSkeletons({ count = 3, label = 'Loading clips…' }) {
  return (
    <section className="card clips" aria-busy="true" aria-label={label}>
      <div className="section-head">
        <span className="skeleton skeleton-title" />
      </div>
      <ol className="clip-grid">
        {Array.from({ length: count }, (_, i) => (
          <li key={i} className="clip clip--skeleton" aria-hidden="true">
            <span className="skeleton skeleton-thumb" />
            <span className="skeleton skeleton-line" />
            <span className="skeleton skeleton-button" />
          </li>
        ))}
      </ol>
    </section>
  )
}

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
  onEditClose,
  onEdited,
  onExportStatus,
  onStartOver,
}) {
  const [clips, setClips] = useState(null)
  const [error, setError] = useState(null)
  const [attempt, setAttempt] = useState(0) // bumped by "Try again"
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
  }, [jobId, attempt])

  function retry() {
    setError(null)
    setAttempt((a) => a + 1)
  }

  if (error) return <ErrorNotice title="We couldn't load the clips" message={error} onRetry={retry} />
  if (!clips) return <ClipSkeletons />

  if (clips.length === 0) {
    return (
      <section className="card empty">
        <p className="empty-title">No clips in this video</p>
        <p>It may be too short or have no picture. Try a longer video.</p>
        <button type="button" onClick={onStartOver}>
          Choose another video
        </button>
      </section>
    )
  }

  return (
    <section className="card clips" aria-labelledby="clips-title">
      <div className="section-head">
        <div>
          <h2 id="clips-title">
            {clips.length} {clips.length === 1 ? 'clip' : 'clips'}
          </h2>
          <p className="section-meta">Tap a clip to play it in the original. Make it vertical, edit it, download it.</p>
        </div>
        <ExportPanel
          jobId={jobId}
          refreshKey={editKey}
          onStarted={() => setSyncKey((k) => k + 1)}
          onStatus={onExportStatus}
        />
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
            onEditClose={onEditClose}
            onEdited={handleEdited}
          />
        ))}
      </ol>
    </section>
  )
}
