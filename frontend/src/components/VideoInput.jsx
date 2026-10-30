import { useState } from 'react'

export default function VideoInput({ onFile, onUrl, disabled }) {
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

  return (
    <div className="input">
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
        <span className="dropzone-title">Drop a video here</span>
        <span className="dropzone-hint">or click to choose a file</span>
      </label>

      <div className="divider" aria-hidden="true">
        <span>or</span>
      </div>

      <form className="url-form" onSubmit={handleSubmit}>
        <label htmlFor="youtube-url" className="visually-hidden">
          YouTube URL
        </label>
        <input
          id="youtube-url"
          type="url"
          inputMode="url"
          placeholder="Paste a YouTube link"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={disabled}
        />
        <button type="submit" disabled={disabled || !url.trim()}>
          Fetch
        </button>
      </form>
    </div>
  )
}
