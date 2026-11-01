import { useState } from 'react'
import { formatLength, formatSize } from '../format.js'

// The formats the server's ffprobe whitelist accepts, by the names people know them by.
const FORMATS = 'MP4, MOV, WebM, MKV or AVI'

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
    <div className="input">
      {limits?.sample_available && (
        <div className="sample">
          <div>
            <p className="sample-title">No video handy?</p>
            <p className="sample-hint">Use a 3-minute sample interview and get clips in one click.</p>
          </div>
          <button type="button" className="sample-button" onClick={onSample} disabled={disabled}>
            <span aria-hidden="true">▶</span> Try a sample video
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
        <svg className="dropzone-icon" viewBox="0 0 24 24" width="32" height="32" aria-hidden="true">
          <path
            d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="dropzone-title">{dragging ? 'Drop it here' : 'Drop a video here'}</span>
        <span className="dropzone-hint">
          or <span className="dropzone-link">choose a file</span>
        </span>
        {limits && (
          <span className="limits">
            {FORMATS} · up to {formatSize(limits.max_upload_mb)} · up to {maxLength} long
          </span>
        )}
      </label>

      <div className="divider" aria-hidden="true">
        <span>or</span>
      </div>

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
          <button type="submit" disabled={disabled || !url.trim()}>
            Fetch
          </button>
        </div>
        <p id="youtube-hint" className="limits">
          Public videos up to {maxLength ?? 'the length limit'}. Live streams and playlists aren't supported.
        </p>
      </form>
    </div>
  )
}
