import { useRef } from 'react'

// A press this close (px) to a handle grabs it where it is, instead of jumping it to the finger.
const GRAB_PX = 24
// Movement (px) that decides which of two overlapping handles a press meant.
const DECIDE_PX = 3

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v))
const round3 = (v) => Math.round(v * 1000) / 1000

// Two handles on one track for a [start, end] range, at least `gap` apart.
// The pointer moves the nearer handle; where the two overlap, the first movement picks one
// (left: start, right: end), so short ranges on a phone stay draggable. Keys move the focused one.
// onChange(start, end, moved) gets the handle that moved, so the caller can show that frame.
export default function RangeSlider({ min, max, start, end, gap, step, marks = [], format, onChange }) {
  const trackRef = useRef(null)
  const startRef = useRef(null)
  const endRef = useRef(null)
  const handleRefs = { start: startRef, end: endRef }
  const drag = useRef(null) // { handle, offset, x, value } while a pointer is down

  const span = max - min || 1
  const pct = (v) => `${((v - min) / span) * 100}%`

  function set(handle, value) {
    if (handle === 'start') onChange(round3(clamp(value, min, end - gap)), end, 'start')
    else onChange(start, round3(clamp(value, start + gap, max)), 'end')
  }

  // Dragging snaps to the step grid; keys step from the current value, which may be off-grid.
  const move = (handle, value) => set(handle, Math.round(value / step) * step)

  function pointerValue(e) {
    const rect = trackRef.current.getBoundingClientRect()
    return { value: min + clamp((e.clientX - rect.left) / rect.width, 0, 1) * span, pxPerSec: rect.width / span }
  }

  function onPointerDown(e) {
    if (e.button !== 0) return
    e.preventDefault() // no text selection or focus jump while dragging
    trackRef.current.setPointerCapture(e.pointerId)
    const { value, pxPerSec } = pointerValue(e)
    const near = (v) => Math.abs(value - v) * pxPerSec <= GRAB_PX
    let handle = null
    let offset = 0
    if (near(start) && near(end)) {
      handle = null // overlapping: wait for the first movement
    } else if (near(start) || near(end)) {
      handle = near(start) ? 'start' : 'end'
      offset = value - (handle === 'start' ? start : end)
    } else {
      handle = value <= start ? 'start' : value >= end ? 'end' : value - start < end - value ? 'start' : 'end'
      move(handle, value)
    }
    drag.current = { handle, offset, x: e.clientX, value }
    if (handle) handleRefs[handle].current.focus({ preventScroll: true })
  }

  function onPointerMove(e) {
    const d = drag.current
    if (!d) return
    if (!d.handle) {
      if (Math.abs(e.clientX - d.x) < DECIDE_PX) return
      d.handle = e.clientX < d.x ? 'start' : 'end'
      d.offset = d.value - (d.handle === 'start' ? start : end)
      handleRefs[d.handle].current.focus({ preventScroll: true })
    }
    move(d.handle, pointerValue(e).value - d.offset)
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
      Home: min,
      End: max,
    }
    if (!(e.key in moves)) return
    e.preventDefault()
    set(handle, moves[e.key])
  }

  const handle = (name, value, lo, hi, label) => (
    <div
      ref={handleRefs[name]}
      className={`range-handle range-handle--${name}`}
      style={{ left: pct(value) }}
      role="slider"
      tabIndex={0}
      aria-label={label}
      aria-valuemin={lo}
      aria-valuemax={hi}
      aria-valuenow={value}
      aria-valuetext={format(value)}
      onKeyDown={(e) => onKeyDown(name, e)}
    />
  )

  return (
    <div
      ref={trackRef}
      className="range"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <div className="range-rail" />
      <div className="range-fill" style={{ left: pct(start), width: `${((end - start) / span) * 100}%` }} />
      {marks
        .filter((m) => m >= min && m <= max)
        .map((m) => (
          <div key={m} className="range-mark" style={{ left: pct(m) }} />
        ))}
      {handle('start', start, min, round3(end - gap), 'Start')}
      {handle('end', end, round3(start + gap), max, 'End')}
    </div>
  )
}
