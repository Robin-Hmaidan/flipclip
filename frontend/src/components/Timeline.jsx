import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { clipNumber, formatTimecode } from '../format.js'

// Never fewer pixels per second than this: a long video scrolls inside the timeline instead of
// squeezing its clips into slivers.
const MIN_PX_PER_SEC = 4
// Room either side of the track, so a handle at the very start or end can still be grabbed.
const PAD_PX = 24
// Ruler labels at least this far apart, and minor ticks at least this far apart.
const LABEL_PX = 84
const TICK_PX = 12
const INTERVALS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600]

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))
const round3 = (v) => Math.round(v * 1000) / 1000

// Ruler ticks: a labelled one every `major` seconds, with up to four unlabelled ones between.
function ticks(duration, pxPerSec) {
  const major = INTERVALS.find((s) => s * pxPerSec >= LABEL_PX) ?? INTERVALS.at(-1)
  const perMajor = [5, 2, 1].find((n) => (major / n) * pxPerSec >= TICK_PX)
  const minor = major / perMajor
  return Array.from({ length: Math.floor(duration / minor) + 1 }, (_, i) => ({
    t: i * minor,
    major: i % perMajor === 0,
  }))
}

// The whole video, each clip a block on it. Pressing a block selects that clip. The selected clip
// gets a handle on each edge: dragging one, or arrow keys while it's focused, moves that end.
// onChange(start, end, moved) gets the handle that moved, so the caller can show that frame.
// Clips may overlap after an edit; the selected one is drawn on top.
export default function Timeline({ clips, duration, selected, start, end, gap, step, videoRef, playingIndex, onSelect, onChange }) {
  const scrollRef = useRef(null)
  const trackRef = useRef(null)
  const playheadRef = useRef(null)
  const startRef = useRef(null)
  const endRef = useRef(null)
  const handleRefs = { start: startRef, end: endRef }
  const drag = useRef(null) // { handle, offset } while a pointer holds a handle
  const [available, setAvailable] = useState(0)

  useLayoutEffect(() => {
    const el = scrollRef.current
    const measure = () => setAvailable(el.clientWidth - 2 * PAD_PX)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  const pxPerSec = Math.max(available / duration, MIN_PX_PER_SEC)
  const x = (t) => t * pxPerSec
  const clip = clips.find((c) => c.index === selected)
  // clip.end can sit a fraction past a rounded duration; the track always contains the clip.
  const max = Math.max(round3(duration), clip?.end ?? 0)

  // The playhead follows the source video. Moved directly, not through state, so playback
  // doesn't re-render every block and tick sixty times a second.
  useEffect(() => {
    const video = videoRef.current
    const head = playheadRef.current
    if (!video || !head) return undefined
    let frame = 0
    const place = () => {
      head.style.transform = `translateX(${video.currentTime * pxPerSec}px)`
    }
    const follow = () => {
      place()
      frame = requestAnimationFrame(follow)
    }
    const onPlay = () => {
      cancelAnimationFrame(frame)
      follow()
    }
    const onPause = () => {
      cancelAnimationFrame(frame)
      place()
    }
    place()
    if (!video.paused) onPlay()
    video.addEventListener('play', onPlay)
    video.addEventListener('pause', onPause)
    video.addEventListener('seeked', place)
    video.addEventListener('timeupdate', place)
    return () => {
      cancelAnimationFrame(frame)
      video.removeEventListener('play', onPlay)
      video.removeEventListener('pause', onPause)
      video.removeEventListener('seeked', place)
      video.removeEventListener('timeupdate', place)
    }
  }, [videoRef, pxPerSec])

  // A newly selected clip (from the film strip, say) scrolls into view if it's off-screen.
  const savedStart = clip?.start
  const savedEnd = clip?.end
  useEffect(() => {
    const el = scrollRef.current
    if (savedStart === undefined || !el) return
    const left = PAD_PX + savedStart * pxPerSec
    const right = PAD_PX + savedEnd * pxPerSec
    if (left < el.scrollLeft || right > el.scrollLeft + el.clientWidth) {
      el.scrollTo({ left: left - Math.max(0, (el.clientWidth - (right - left)) / 2), behavior: 'smooth' })
    }
  }, [selected, savedStart, savedEnd, pxPerSec])

  function set(handle, value) {
    if (handle === 'start') onChange(round3(clamp(value, 0, end - gap)), end, 'start')
    else onChange(start, round3(clamp(value, start + gap, max)), 'end')
  }

  // Dragging snaps to the step grid; keys step from the current value, which may be off-grid.
  const move = (handle, value) => set(handle, Math.round(value / step) * step)

  const pointerTime = (e) => (e.clientX - trackRef.current.getBoundingClientRect().left) / pxPerSec

  function onPointerDown(handle, e) {
    if (e.button !== 0) return
    e.preventDefault() // no text selection or focus jump while dragging
    e.currentTarget.setPointerCapture(e.pointerId)
    e.currentTarget.focus({ preventScroll: true })
    drag.current = { handle, offset: pointerTime(e) - (handle === 'start' ? start : end) }
  }

  function onPointerMove(e) {
    const d = drag.current
    if (d) move(d.handle, pointerTime(e) - d.offset)
  }

  function onPointerUp() {
    drag.current = null
  }

  function onKeyDown(handle, e) {
    const value = handle === 'start' ? start : end
    const moves = {
      ArrowLeft: value - step,
      ArrowDown: value - step,
      ArrowRight: value + step,
      ArrowUp: value + step,
      PageDown: value - 1,
      PageUp: value + 1,
      Home: 0,
      End: max,
    }
    if (!(e.key in moves)) return
    e.preventDefault()
    set(handle, moves[e.key])
  }

  const handle = (name, value, lo, hi) => (
    <div
      ref={handleRefs[name]}
      className={`tl-handle tl-handle--${name}`}
      style={{ left: x(value) }}
      role="slider"
      tabIndex={0}
      aria-label={`${name === 'start' ? 'Start' : 'End'} of clip ${selected + 1}`}
      aria-valuemin={lo}
      aria-valuemax={hi}
      aria-valuenow={value}
      aria-valuetext={formatTimecode(value)}
      onKeyDown={(e) => onKeyDown(name, e)}
      onPointerDown={(e) => onPointerDown(name, e)}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    />
  )

  const width = x(duration)

  return (
    <section className="timeline" aria-labelledby="timeline-title">
      <div className="panel-head">
        <h2 id="timeline-title" className="label">
          Timeline
        </h2>
        <span className="mono meta">
          {clips.length} {clips.length === 1 ? 'clip' : 'clips'} · {formatTimecode(duration)}
        </span>
      </div>
      <div className="tl-scroll" ref={scrollRef}>
        <div className="tl-inner" style={{ width: width + 2 * PAD_PX, paddingInline: PAD_PX }}>
          <div className="tl-ruler" aria-hidden="true">
            {ticks(duration, pxPerSec).map(({ t, major }) => (
              <span key={t} className={`tl-tick${major ? ' tl-tick--major' : ''}`} style={{ left: x(t) }}>
                {major && (duration - t) * pxPerSec >= LABEL_PX * 0.75 && (
                  <span className="tl-tick-label">{formatTimecode(t, false)}</span>
                )}
              </span>
            ))}
          </div>
          <div className="tl-track" ref={trackRef}>
            {clips.map((c) => {
              const isSelected = c.index === selected
              const s = isSelected ? start : c.start
              const e = isSelected ? end : c.end
              return (
                <button
                  key={c.index}
                  type="button"
                  className={`tl-clip${isSelected ? ' tl-clip--selected' : ''}${c.index === playingIndex ? ' tl-clip--playing' : ''}`}
                  style={{ left: x(s), width: x(e) - x(s) }}
                  aria-pressed={isSelected}
                  aria-label={`Clip ${c.index + 1}, ${formatTimecode(s)} to ${formatTimecode(e)}`}
                  onClick={() => onSelect(c)}
                >
                  <span className="tl-clip-num">{clipNumber(c.index)}</span>
                </button>
              )
            })}
            {clip?.edited &&
              [clip.original_start, clip.original_end].map((t) => (
                <span key={t} className="tl-mark" style={{ left: x(t) }} aria-hidden="true" />
              ))}
            {clip && (
              <>
                {handle('start', start, 0, round3(end - gap))}
                {handle('end', end, round3(start + gap), max)}
              </>
            )}
            <span ref={playheadRef} className="tl-playhead" aria-hidden="true" />
          </div>
        </div>
      </div>
    </section>
  )
}
