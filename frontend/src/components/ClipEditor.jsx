import { clipNumber, formatSeconds, formatTimecode } from '../format.js'

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

// The selected clip's cut, under the timeline: exact times, ±1 s buttons, and Save once it changed.
// The handles on the timeline move the same start and end.
export default function ClipEditor({
  clip,
  start,
  end,
  limits,
  busy,
  saving,
  error,
  playing,
  onNudge,
  onPlay,
  onSave,
  onCancel,
  onReset,
}) {
  const changed = start !== clip.start || end !== clip.end
  const problem = rangeProblem(start, end, limits)
  const blocker = busy ? 'This clip is being made vertical. You can save once that has finished.' : problem

  const bound = (handle, label, value) => (
    <div className="cut-bound">
      <span className="label">{label}</span>
      <div className="cut-bound-controls">
        <button type="button" className="secondary" onClick={() => onNudge(handle, -1)} aria-label={`${label} 1 second earlier`}>
          −1 s
        </button>
        <output className="mono cut-time">{formatTimecode(value)}</output>
        <button type="button" className="secondary" onClick={() => onNudge(handle, 1)} aria-label={`${label} 1 second later`}>
          +1 s
        </button>
      </div>
    </div>
  )

  return (
    <section className="cut" aria-labelledby="cut-title">
      <div className="panel-head">
        <h2 id="cut-title" className="label">
          Cut · Clip {clipNumber(clip.index)}
        </h2>
        <span className="meta">Drag the edges on the timeline, or use the buttons.</span>
      </div>

      <div className="cut-row">
        {bound('start', 'Start', start)}
        {bound('end', 'End', end)}
        <div className="cut-bound">
          <span className="label">Length</span>
          <output className="mono cut-time cut-length">{formatSeconds(end - start)}</output>
        </div>
      </div>

      {clip.edited && (
        <p className="hint">
          Original cut <span className="mono">{formatTimecode(clip.original_start)}–{formatTimecode(clip.original_end)}</span>,
          dashed on the timeline.
        </p>
      )}
      {changed && blocker && (
        <p id="cut-problem" className="problem" role="status">
          {blocker}
        </p>
      )}
      {error && (
        <p className="problem" role="alert">
          {error}
        </p>
      )}

      <div className="button-row">
        <button type="button" className="secondary" onClick={onPlay}>
          {playing ? 'Stop' : 'Play selection'}
        </button>
        {clip.edited && (
          <button type="button" className="secondary" disabled={saving || busy} onClick={onReset}>
            Reset to original
          </button>
        )}
        {changed && (
          <>
            <button type="button" className="secondary" disabled={saving} onClick={onCancel}>
              Cancel
            </button>
            <button
              type="button"
              disabled={saving || Boolean(blocker)}
              aria-describedby={blocker ? 'cut-problem' : undefined}
              onClick={onSave}
            >
              {saving ? 'Saving…' : 'Save cut'}
            </button>
          </>
        )}
      </div>
    </section>
  )
}
