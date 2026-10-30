import { formatTime } from '../format.js'
import { useClipRender } from '../useClipRender.js'
import { ProgressBar } from './JobStatus.jsx'

export default function ClipCard({ jobId, clip, playing, showing, onPlay, onShowVertical, onRendered }) {
  const render = useClipRender(jobId, clip.index, (url) => onRendered(clip, url))
  const busy = render.status === 'queued' || render.status === 'rendering'

  return (
    <li className={`clip${playing ? ' clip--playing' : ''}${showing ? ' clip--showing' : ''}`}>
      <button type="button" className="clip-play" aria-pressed={playing} onClick={() => onPlay(clip)}>
        <img src={clip.thumbnail_url} alt="" loading="lazy" width="320" height="180" />
        <span className="clip-time">
          {formatTime(clip.start)}–{formatTime(clip.end)}
        </span>
        <span className="clip-duration">{formatTime(clip.duration)}</span>
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
          <button type="button" className="small" onClick={() => onShowVertical(clip, render.video_url)}>
            {showing ? 'Showing vertical' : 'Show vertical'}
          </button>
        )}
        {render.status === 'failed' && (
          <>
            <p className="clip-error">{render.error}</p>
            <button type="button" className="small" onClick={render.start}>
              Try again
            </button>
          </>
        )}
      </div>
    </li>
  )
}
