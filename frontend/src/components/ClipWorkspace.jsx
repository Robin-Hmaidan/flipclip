import { useCallback, useEffect, useState } from 'react'
import { editClip, getClips, resetClip } from '../api.js'
import ClipCard from './ClipCard.jsx'
import ClipEditor from './ClipEditor.jsx'
import ExportPanel from './ExportPanel.jsx'
import ErrorNotice from './Notice.jsx'
import Timeline from './Timeline.jsx'

const STEP_SEC = 0.1
const round3 = (t) => Math.round(t * 1000) / 1000

// Grey stand-ins with the film strip's shape, so the page doesn't jump when the clips arrive.
export function ClipSkeletons({ count = 3, label = 'Loading clips…' }) {
  return (
    <section className="clips" aria-busy="true" aria-label={label}>
      <ol className="strip">
        {Array.from({ length: count }, (_, i) => (
          <li key={i} className="frame frame--skeleton" aria-hidden="true">
            <span className="frame-film">
              <span className="frame-picture skeleton" />
            </span>
            <span className="skeleton skeleton-line" />
          </li>
        ))}
      </ol>
    </section>
  )
}

// Everything once the clips exist: the timeline under the source, the selected clip's cut,
// the film strip, and export. The source video itself (videoRef) belongs to the page.
export default function ClipWorkspace({
  jobId,
  duration,
  limits,
  videoRef,
  playingIndex,
  showingIndex,
  onPlay,
  onStop,
  onShowVertical,
  onRendered,
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
  const [selected, setSelected] = useState(0)
  const [draft, setDraft] = useState(null) // { start, end } of the selected clip while it's being changed
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState(null)
  const [busy, setBusy] = useState({}) // clip index -> true while it's being made vertical

  useEffect(() => {
    let cancelled = false
    getClips(jobId)
      .then((list) => !cancelled && setClips(list))
      .catch((err) => !cancelled && setError(err.message))
    return () => {
      cancelled = true
    }
  }, [jobId, attempt])

  const reportBusy = useCallback((index, isBusy) => {
    setBusy((prev) => (Boolean(prev[index]) === isBusy ? prev : { ...prev, [index]: isBusy }))
  }, [])

  function retry() {
    setError(null)
    setAttempt((a) => a + 1)
  }

  if (error) return <ErrorNotice title="Couldn't load the clips" message={error} onRetry={retry} />
  if (!clips) return <ClipSkeletons />

  if (clips.length === 0) {
    return (
      <section className="empty">
        <p className="empty-title">No clips found</p>
        <p>The video may be too short or have no picture. Try a longer one.</p>
        <button type="button" onClick={onStartOver}>
          Choose another video
        </button>
      </section>
    )
  }

  const clip = clips.find((c) => c.index === selected)
  const start = draft?.start ?? clip.start
  const end = draft?.end ?? clip.end

  // Park the source on a frame, so the user sees where a cut lands.
  function showFrame(t) {
    onStop()
    const video = videoRef.current
    if (video) {
      video.pause()
      video.currentTime = t
    }
  }

  function select(next, play) {
    if (next.index !== selected) {
      setSelected(next.index)
      setDraft(null)
      setSaveError(null)
    }
    // The selected clip plays with its unsaved cut, so the user hears what they'd save.
    const bounds = next.index === selected ? { ...next, start, end } : next
    if (play) onPlay(bounds)
    else showFrame(bounds.start)
  }

  function change(nextStart, nextEnd, moved) {
    setDraft({ start: nextStart, end: nextEnd })
    setSaveError(null)
    showFrame(moved === 'start' ? nextStart : nextEnd)
  }

  function nudge(handle, delta) {
    const max = Math.max(round3(duration), clip.end)
    if (handle === 'start') change(round3(Math.min(Math.max(start + delta, 0), end - STEP_SEC)), end, 'start')
    else change(start, round3(Math.max(Math.min(end + delta, max), start + STEP_SEC)), 'end')
  }

  function togglePlay() {
    if (playingIndex === selected) {
      onStop()
      videoRef.current?.pause()
    } else {
      onPlay({ index: selected, start, end })
    }
  }

  async function submit(call) {
    setSaving(true)
    setSaveError(null)
    try {
      const saved = await call()
      setClips((list) => list.map((c) => (c.index === saved.index ? saved : c)))
      setDraft(null)
      setEditKey((k) => k + 1)
      onEdited(saved)
    } catch (err) {
      setSaveError(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <Timeline
        clips={clips}
        duration={duration}
        selected={selected}
        start={start}
        end={end}
        gap={STEP_SEC}
        step={STEP_SEC}
        videoRef={videoRef}
        playingIndex={playingIndex}
        onSelect={(c) => select(c, false)}
        onChange={change}
      />

      <ClipEditor
        clip={clip}
        start={start}
        end={end}
        limits={limits}
        busy={Boolean(busy[clip.index])}
        saving={saving}
        error={saveError}
        playing={playingIndex === selected}
        onNudge={nudge}
        onPlay={togglePlay}
        onSave={() => submit(() => editClip(jobId, clip.index, start, end))}
        onCancel={() => {
          setDraft(null)
          setSaveError(null)
        }}
        onReset={() => submit(() => resetClip(jobId, clip.index))}
      />

      <section className="clips" aria-labelledby="clips-title">
        <div className="panel-head">
          <h2 id="clips-title" className="label">
            Clips
          </h2>
          <span className="meta">Press a clip to play it. Make it vertical, then download it.</span>
        </div>
        <ol className="strip">
          {clips.map((c) => (
            <ClipCard
              // New bounds remount the card: its render was dropped, so its state starts over.
              key={`${c.index}:${c.start}:${c.end}`}
              jobId={jobId}
              clip={c}
              selected={c.index === selected}
              playing={c.index === playingIndex}
              showing={c.index === showingIndex}
              syncKey={syncKey}
              onSelect={(next) => select(next, true)}
              onShowVertical={onShowVertical}
              onRendered={onRendered}
              onBusy={reportBusy}
            />
          ))}
        </ol>
      </section>

      <ExportPanel
        jobId={jobId}
        count={clips.length}
        refreshKey={editKey}
        onStarted={() => setSyncKey((k) => k + 1)}
        onStatus={onExportStatus}
      />
    </>
  )
}
