import { useEffect, useRef } from 'react'
import { clipNumber, formatSeconds, formatTimecode } from '../format.js'
import { useClipRender } from '../useClipRender.js'
import { ProgressBar } from './JobStatus.jsx'

// One frame of the film strip: pressing the picture selects the clip and plays it in the source.
// onBusy(index, busy) tells the editor whether this clip is being made vertical, which blocks saving.
export default function ClipCard({
  jobId,
  clip,
  selected,
  playing,
  showing,
  syncKey,
  onSelect,
  onShowVertical,
  onRendered,
  onBusy,
}) {
  const render = useClipRender(jobId, clip.index, (done) => onRendered(clip, done), syncKey)
  const busy = render.status === 'queued' || render.status === 'rendering'

  useEffect(() => {
    onBusy(clip.index, busy)
  }, [clip.index, busy, onBusy])

  // Selected from the timeline: bring this frame into view within the strip, without moving the page.
  const itemRef = useRef(null)
  useEffect(() => {
    const item = itemRef.current
    const strip = item?.parentElement
    if (!selected || !strip) return
    const left = item.offsetLeft
    if (left < strip.scrollLeft || left + item.offsetWidth > strip.scrollLeft + strip.clientWidth) {
      strip.scrollTo({ left, behavior: 'smooth' })
    }
  }, [selected])

  const state = showing ? 'In the phone' : playing ? 'Playing' : null

  return (
    <li ref={itemRef} className={`frame${selected ? ' frame--selected' : ''}`}>
      <button
        type="button"
        className="frame-select"
        aria-pressed={selected}
        aria-label={`Clip ${clip.index + 1}, ${formatSeconds(clip.duration)}: select and play`}
        onClick={() => onSelect(clip)}
      >
        <span className="frame-film">
          <span className="frame-picture">
            <img src={clip.thumbnail_url} alt="" loading="lazy" width="320" height="180" />
            <span className="frame-num mono">{clipNumber(clip.index)}</span>
            <span className="frame-len mono">{formatSeconds(clip.duration)}</span>
          </span>
        </span>
        <span className="frame-info">
          <span className="mono">
            {formatTimecode(clip.start)}–{formatTimecode(clip.end)}
          </span>
          <span className="frame-tags">
            {clip.edited && <span className="tag">Edited</span>}
            {state && <span className="tag tag--live">{state}</span>}
          </span>
        </span>
      </button>

      <div className="frame-actions">
        {render.status === 'idle' && (
          <button type="button" className="secondary" onClick={render.start}>
            Make vertical
          </button>
        )}
        {busy && (
          <ProgressBar label={render.status === 'queued' ? 'Waiting…' : 'Making vertical…'} value={render.progress} />
        )}
        {render.status === 'done' && (
          <>
            <button type="button" className="secondary" aria-pressed={showing} onClick={() => onShowVertical(clip, render)}>
              {showing ? 'Showing in phone' : 'Show in phone'}
            </button>
            <a className="button secondary" href={render.download_url} download>
              Download clip
            </a>
          </>
        )}
        {render.status === 'failed' && (
          <>
            <p className="problem" role="alert">
              {render.error || "Couldn't make this clip vertical."}
            </p>
            <button type="button" onClick={render.start}>
              Try again
            </button>
          </>
        )}
      </div>
    </li>
  )
}
