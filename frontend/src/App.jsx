import { useEffect, useState } from 'react'
import { getConfig, getHealth, segmentJob, submitYoutube, uploadVideo } from './api.js'
import ClipList from './components/ClipList.jsx'
import JobStatus, { ProgressBar } from './components/JobStatus.jsx'
import Preview from './components/Preview.jsx'
import VideoInput from './components/VideoInput.jsx'
import { useJob } from './useJob.js'
import { useRangePlayback } from './useRangePlayback.js'

// Statuses in which the job has a playable video.
const HAS_VIDEO = ['ready', 'segmenting', 'segmented']

export default function App() {
  const [health, setHealth] = useState(null)
  const [config, setConfig] = useState(null)
  const [uploadPct, setUploadPct] = useState(null) // null when no upload is running
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)
  const [jobId, setJobId] = useState(null)
  const { job, error: pollError, resume } = useJob(jobId)
  const { videoRef, playRange, activeIndex, onSeeking, stop } = useRangePlayback()

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null))
    getConfig().then(setConfig).catch(() => setConfig(null))
  }, [])

  const hasVideo = job && HAS_VIDEO.includes(job.status)

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

  async function findClips() {
    setError(null)
    setSubmitting(true)
    try {
      await segmentJob(job.id)
      resume()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  function reset() {
    stop()
    setJobId(null)
    setError(null)
  }

  const shownError = error || pollError
  const settled = job && ['ready', 'failed', 'segmented'].includes(job.status)

  return (
    <main className="app">
      <header>
        <h1>FlipClip</h1>
        <p className="tagline">Turn horizontal videos into vertical clips.</p>
      </header>

      {!jobId && <VideoInput onFile={handleFile} onUrl={(url) => start(() => submitYoutube(url))} disabled={submitting} />}

      {uploadPct !== null && (
        <ProgressBar label={uploadPct < 100 ? 'Uploading…' : 'Checking video…'} value={uploadPct} />
      )}
      {submitting && uploadPct === null && !jobId && <p className="message">Checking link…</p>}
      {job && !hasVideo && <JobStatus job={job} />}

      {hasVideo && (
        <>
          <Preview job={job} videoRef={videoRef} onSeeking={onSeeking} />
          {job.status === 'ready' && job.error && <p className="message message--error">{job.error}</p>}
          {job.status === 'ready' && (
            <button type="button" className="primary" onClick={findClips} disabled={submitting}>
              Find clips
            </button>
          )}
          {job.status === 'segmenting' && <ProgressBar label="Finding clips…" value={job.progress} />}
          {job.status === 'segmented' && (
            <ClipList key={job.id} jobId={job.id} activeIndex={activeIndex} onSelect={playRange} />
          )}
        </>
      )}

      {shownError && (
        <p className="message message--error" role="alert">
          {shownError}
        </p>
      )}

      {(settled || pollError) && (
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
