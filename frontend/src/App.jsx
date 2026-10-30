import { useEffect, useState } from 'react'
import { getConfig, getHealth, submitYoutube, uploadVideo } from './api.js'
import JobStatus, { ProgressBar } from './components/JobStatus.jsx'
import VideoInput from './components/VideoInput.jsx'
import { useJob } from './useJob.js'

export default function App() {
  const [health, setHealth] = useState(null)
  const [config, setConfig] = useState(null)
  const [uploadPct, setUploadPct] = useState(null) // null when no upload is running
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [jobId, setJobId] = useState(null)
  const { job, error: pollError } = useJob(jobId)

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null))
    getConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  const busy = submitting || (jobId && !['ready', 'failed'].includes(job?.status))

  async function start(submit) {
    setError(null)
    setJobId(null)
    setSubmitting(true)
    try {
      const created = await submit()
      setJobId(created.id)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
      setUploadPct(null)
    }
  }

  function handleFile(file) {
    // Checked here too so a huge file fails instantly, not after minutes of uploading.
    if (config && file.size > config.max_upload_mb * 1024 * 1024) {
      setError(`File is larger than ${config.max_upload_mb} MB.`)
      return
    }
    setUploadPct(0)
    start(() => uploadVideo(file, setUploadPct))
  }

  function handleUrl(url) {
    start(() => submitYoutube(url))
  }

  function reset() {
    setJobId(null)
    setError(null)
  }

  const shownError = error || pollError

  return (
    <main className="app">
      <header>
        <h1>FlipClip</h1>
        <p className="tagline">Turn horizontal videos into vertical clips.</p>
      </header>

      {!jobId && <VideoInput onFile={handleFile} onUrl={handleUrl} disabled={busy} />}

      <section className="status" aria-live="polite">
        {uploadPct !== null && (
          <ProgressBar label={uploadPct < 100 ? 'Uploading…' : 'Checking video…'} value={uploadPct} />
        )}
        {submitting && uploadPct === null && <p className="message">Checking link…</p>}
        {shownError && <p className="message message--error">{shownError}</p>}
        {job && <JobStatus job={job} />}
      </section>

      {(job?.status === 'ready' || job?.status === 'failed' || pollError) && (
        <button type="button" className="secondary" onClick={reset}>
          Start over
        </button>
      )}

      <footer>
        {health ? `Backend ${health.status} · ffmpeg ${health.ffmpeg_version ?? 'not found'}` : 'Backend unreachable'}
      </footer>
    </main>
  )
}
