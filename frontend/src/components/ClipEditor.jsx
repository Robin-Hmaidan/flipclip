import { useEffect, useRef, useState } from 'react'
import { editClip, resetClip } from '../api.js'
import { formatPrecise } from '../format.js'
import { useRangePlayback } from '../useRangePlayback.js'
import RangeSlider from './RangeSlider.jsx'

// Footage either side of the clip that the handles can reach.
const WINDOW_SEC = 30
const NUDGE_SEC = 1
const STEP_SEC = 0.1

const round3 = (t) => Math.round(t * 1000) / 1000

// Why [start, end] can't be saved, or null. Mirrors the server's check, which has the final say.
function rangeProblem(start, end, limits) {
  if (!limits) return null
  const length = round3(end - start)
  if (length < limits.edit_min_sec) {
    return `Too short: a clip must be at least ${limits.edit_min_sec} s long (this one is ${length.toFixed(1)} s).`
  }
  if (length > limits.max_clip_sec) {
    return `Too long: a clip can be at most ${limits.max_clip_sec} s long (this one is ${length.toFixed(1)} s).`
  }
  return null
}

// Modal editor for one clip's bounds. onSaved gets the clip as the server stored it.
export default function ClipEditor({ jobId, clip, duration, limits, busy, onSaved, onClose }) {
  const dialogRef = useRef(null)
  const [start, setStart] = useState(clip.start)
  const [end, setEnd] = useState(clip.end)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const { videoRef, playRange, activeIndex, onSeeking, stop } = useRangePlayback()
  const playing = activeIndex !== null

  // Fixed while the editor is open, so the track doesn't rescale under the finger.
  // clip.end can sit a fraction past a rounded duration; the window always contains the clip.
  const [range] = useState(() => ({
    min: Math.max(0, clip.start - WINDOW_SEC),
    max: Math.max(clip.end, Math.min(round3(duration), clip.end + WINDOW_SEC)),
  }))

  useEffect(() => {
    dialogRef.current.showModal()
  }, [])

  // Show the frame at the handle being moved, so the user sees where the cut lands.
  function change(nextStart, nextEnd, moved) {
    setStart(nextStart)
    setEnd(nextEnd)
    setError(null)
    stop()
    const video = videoRef.current
    if (video) {
      video.pause()
      video.currentTime = moved === 'start' ? nextStart : nextEnd
    }
  }

  function nudge(handle, delta) {
    if (handle === 'start') change(round3(Math.min(Math.max(start + delta, range.min), end - STEP_SEC)), end, 'start')
    else change(start, round3(Math.max(Math.min(end + delta, range.max), start + STEP_SEC)), 'end')
  }

  function togglePlay() {
    if (playing) {
      stop()
      videoRef.current?.pause()
    } else {
      playRange({ index: clip.index, start, end })
    }
  }

  async function submit(call) {
    setSaving(true)
    setError(null)
    try {
      onSaved(await call())
    } catch (err) {
      setError(err.message)
      setSaving(false)
    }
  }

  const changed = start !== clip.start || end !== clip.end
  const problem = rangeProblem(start, end, limits)
  const blocker = busy ? 'This clip is being made vertical. You can save once that has finished.' : problem

  function save() {
    if (!changed) onClose()
    else submit(() => editClip(jobId, clip.index, start, end))
  }

  const bound = (handle, label, value) => (
    <div className="editor-bound">
      <span className="editor-bound-label">{label}</span>
      <button type="button" className="small secondary" onClick={() => nudge(handle, -NUDGE_SEC)}>
        −1 s
      </button>
      <output className="editor-time">{formatPrecise(value)}</output>
      <button type="button" className="small secondary" onClick={() => nudge(handle, NUDGE_SEC)}>
        +1 s
      </button>
    </div>
  )

  return (
    <dialog
      ref={dialogRef}
      className="editor"
      aria-labelledby="editor-title"
      onCancel={(e) => {
        e.preventDefault() // Escape: close through React, so state and DOM agree
        onClose()
      }}
    >
      <h2 id="editor-title">Edit clip {clip.index + 1}</h2>

      <video
        ref={videoRef}
        src={`/api/jobs/${jobId}/video#t=${clip.start}`}
        playsInline
        preload="auto"
        onSeeking={onSeeking}
      />
      <button type="button" className="small editor-play" onClick={togglePlay}>
        {playing ? 'Stop' : 'Play selection'}
      </button>

      <RangeSlider
        min={range.min}
        max={range.max}
        start={start}
        end={end}
        gap={STEP_SEC}
        step={STEP_SEC}
        marks={clip.edited ? [clip.original_start, clip.original_end] : []}
        format={formatPrecise}
        onChange={change}
      />
      <div className="editor-scale">
        <span>{formatPrecise(range.min)}</span>
        <span>{formatPrecise(range.max)}</span>
      </div>

      <div className="editor-bounds">
        {bound('start', 'Start', start)}
        {bound('end', 'End', end)}
      </div>
      <p className="editor-length">
        Length <strong>{(end - start).toFixed(1)} s</strong>
        {clip.edited && (
          <>
            {' '}
            · original {formatPrecise(clip.original_start)}–{formatPrecise(clip.original_end)} (marked on the track)
          </>
        )}
      </p>

      {blocker && (
        <p id="editor-problem" className="editor-problem" role="status">
          {blocker}
        </p>
      )}
      {error && (
        <p className="message message--error" role="alert">
          {error}
        </p>
      )}

      <div className="editor-actions">
        {clip.edited && (
          <button
            type="button"
            className="secondary editor-reset"
            disabled={saving || busy}
            onClick={() => submit(() => resetClip(jobId, clip.index))}
          >
            Reset to original
          </button>
        )}
        <button type="button" className="secondary" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          disabled={saving || Boolean(blocker)}
          aria-describedby={blocker ? 'editor-problem' : undefined}
          onClick={save}
        >
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </dialog>
  )
}
