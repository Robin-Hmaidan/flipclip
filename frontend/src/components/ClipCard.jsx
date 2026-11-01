import { useState } from 'react'
import { formatPrecise } from '../format.js'
import { useClipRender } from '../useClipRender.js'
import ClipEditor from './ClipEditor.jsx'
import { ProgressBar } from './JobStatus.jsx'

export default function ClipCard({
  jobId,
  clip,
  duration,
  limits,
  playing,
  showing,
  syncKey,
  onPlay,
  onShowVertical,
  onRendered,
  onEditOpen,
  onEditClose,
  onEdited,
}) {
  const render = useClipRender(jobId, clip.index, (done) => onRendered(clip, done), syncKey)
  const busy = render.status === 'queued' || render.status === 'rendering'
  const [editing, setEditing] = useState(false)

  function openEditor() {
    onEditOpen()
    setEditing(true)
  }

  function closeEditor() {
    setEditing(false)
    onEditClose()
  }

  return (
    <li className={`clip${playing ? ' clip--playing' : ''}${showing ? ' clip--showing' : ''}`}>
      <button
        type="button"
        className="clip-play"
        aria-pressed={playing}
        aria-label={`Play clip ${clip.index + 1} in the original`}
        onClick={() => onPlay(clip)}
      >
        <span className="clip-thumb">
          <img src={clip.thumbnail_url} alt="" loading="lazy" width="320" height="180" />
          <span className="clip-number">{clip.index + 1}</span>
          <span className="clip-length">{clip.duration.toFixed(1)} s</span>
        </span>
        <span className="clip-time">
          {formatPrecise(clip.start)}–{formatPrecise(clip.end)}
          {clip.edited && <span className="clip-tag">edited</span>}
        </span>
      </button>

      <div className="clip-actions">
        {render.status === 'idle' && (
          <button type="button" className="small" onClick={render.start}>
            Make vertical
          </button>
        )}
        {busy && (
          <ProgressBar label={render.status === 'queued' ? 'Waiting…' : 'Making vertical…'} value={render.progress} />
        )}
        {render.status === 'done' && (
          <>
            <button type="button" className="small" onClick={() => onShowVertical(clip, render)}>
              {showing ? 'Showing above' : 'Before / after'}
            </button>
            <a className="button small secondary" href={render.download_url} download>
              Download
            </a>
          </>
        )}
        {render.status === 'failed' && (
          <>
            <p className="clip-error" role="alert">
              {render.error || "Couldn't make this clip vertical."}
            </p>
            <button type="button" className="small" onClick={render.start}>
              Try again
            </button>
          </>
        )}
        <button type="button" className="small secondary" onClick={openEditor}>
          Edit
        </button>
      </div>

      {editing && (
        <ClipEditor
          jobId={jobId}
          clip={clip}
          duration={duration}
          limits={limits}
          busy={busy}
          onSaved={(saved) => {
            closeEditor()
            onEdited(saved)
          }}
          onClose={closeEditor}
        />
      )}
    </li>
  )
}
