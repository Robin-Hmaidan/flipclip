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
  onEdited,
}) {
  const render = useClipRender(jobId, clip.index, (url) => onRendered(clip, url), syncKey)
  const busy = render.status === 'queued' || render.status === 'rendering'
  const [editing, setEditing] = useState(false)

  function openEditor() {
    onEditOpen()
    setEditing(true)
  }

  return (
    <li className={`clip${playing ? ' clip--playing' : ''}${showing ? ' clip--showing' : ''}`}>
      <button type="button" className="clip-play" aria-pressed={playing} onClick={() => onPlay(clip)}>
        <img src={clip.thumbnail_url} alt="" loading="lazy" width="320" height="180" />
        <span className="clip-time">
          {formatPrecise(clip.start)}–{formatPrecise(clip.end)}
        </span>
        <span className="clip-duration">
          {clip.duration.toFixed(1)} s{clip.edited && <span className="clip-tag">edited</span>}
        </span>
      </button>

      <div className="clip-actions">
        {render.status === 'idle' && (
          <button type="button" className="small" onClick={render.start}>
            Make vertical
          </button>
        )}
        {busy && (
          <ProgressBar label={render.status === 'queued' ? 'Waiting…' : 'Rendering…'} value={render.progress} />
        )}
        {render.status === 'done' && (
          <>
            <button type="button" className="small" onClick={() => onShowVertical(clip, render.video_url)}>
              {showing ? 'Showing vertical' : 'Show vertical'}
            </button>
            <a className="button small secondary" href={render.download_url} download>
              Download
            </a>
          </>
        )}
        {render.status === 'failed' && (
          <>
            <p className="clip-error">{render.error}</p>
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
            setEditing(false)
            onEdited(saved)
          }}
          onClose={() => setEditing(false)}
        />
      )}
    </li>
  )
}
