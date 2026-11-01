import { useState } from 'react'
import { formatLength, formatSize } from '../format.js'

// The formats the server's ffprobe whitelist accepts, by the names people know them by.
const FORMATS = 'MP4, MOV, WebM, MKV, AVI'

export default function VideoInput({ limits, onFile, onUrl, onSample, disabled }) {
  const [dragging, setDragging] = useState(false)
  const [url, setUrl] = useState('')

  function handleDrop(e) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file && !disabled) onFile(file)
  }

  function handleSubmit(e) {
    e.preventDefault()
    if (url.trim()) onUrl(url.trim())
  }

  const maxLength = limits && formatLength(limits.max_duration_sec)

  return (
    <div className="import-options">
      {limits?.sample_available && (
        <div className="sample">
          <div>
            <p className="sample-title">Sample interview</p>
            <p className="sample-meta">
              <span className="mono">00:02:45</span> · finds clips right away
            </p>
          </div>
          <button type="button" onClick={onSample} disabled={disabled}>
            Try the sample video
          </button>
        </div>
      )}

      {/* A label, so tapping it opens the file picker on phones where drag-and-drop doesn't exist. */}
      <label
        className={`dropzone${dragging ? ' dropzone--active' : ''}${disabled ? ' dropzone--disabled' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept="video/*"
          className="visually-hidden"
          disabled={disabled}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) onFile(file)
            e.target.value = '' // allow picking the same file again
          }}
        />
        <span className="dropzone-title">{dragging ? 'Drop to upload' : 'Drop a video file here'}</span>
        <span className="dropzone-action">or choose a file</span>
        {limits && (
          <span className="hint mono limits">
            <span>{FORMATS}</span> · <span>max {formatSize(limits.max_upload_mb)}</span> · <span>max {maxLength}</span>
          </span>
        )}
      </label>

      <form className="url-form" onSubmit={handleSubmit}>
        <label htmlFor="youtube-url" className="field-label">
          YouTube link
        </label>
        <div className="url-row">
          <input
            id="youtube-url"
            type="url"
            inputMode="url"
            placeholder="https://www.youtube.com/watch?v=…"
            aria-describedby="youtube-hint"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={disabled}
          />
          <button type="submit" className="secondary" disabled={disabled || !url.trim()}>
            Import video
          </button>
        </div>
        <p id="youtube-hint" className="hint">
          Public videos up to {maxLength ?? 'the length limit'}. No live streams or playlists.
        </p>
      </form>
    </div>
  )
}
