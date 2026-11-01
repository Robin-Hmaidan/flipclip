import { useEffect, useRef, useState } from 'react'
import {
  getConfig,
  isBusy,
  JOB_MISSING,
  segmentJob,
  setJobMissingHandler,
  startSample,
  submitYoutube,
  uploadVideo,
} from './api.js'
import ClipWorkspace, { ClipSkeletons } from './components/ClipWorkspace.jsx'
import JobStatus, { ProgressBar } from './components/JobStatus.jsx'
import Logo from './components/Logo.jsx'
import ErrorNotice from './components/Notice.jsx'
import Preview from './components/Preview.jsx'
import Steps from './components/Steps.jsx'
import VideoInput from './components/VideoInput.jsx'
import { formatSize } from './format.js'
import { useJob } from './useJob.js'
import { useRangePlayback } from './useRangePlayback.js'

// Statuses in which the job has a playable video.
const HAS_VIDEO = ['ready', 'segmenting', 'segmented']

const BUSY_TITLE = 'FlipClip is busy right now'

// What to show for a failed request: the busy notice when the server is full, otherwise the given title.
function failure(err, title, retry) {
  return isBusy(err)
    ? { title: BUSY_TITLE, message: err.message, retry, tone: 'busy' }
    : { title, message: err.message, retry }
}

// The step the user is on: what they're doing now, not the furthest they've been.
function currentStep({ hasVideo, vertical, exportStatus }) {
  if (exportStatus !== 'idle') return 'export'
  if (vertical) return 'reframe'
  return hasVideo ? 'cut' : 'import'
}

function Working({ children }) {
  return (
    <p className="working">
      <span className="spinner" aria-hidden="true" />
      {children}
    </p>
  )
}

export default function App() {
  const [config, setConfig] = useState(null)
  const [configError, setConfigError] = useState(null)
  const [configAttempt, setConfigAttempt] = useState(0)
  const [uploadPct, setUploadPct] = useState(null) // null when no upload is running
  const [pending, setPending] = useState(null) // label while a new job is being created
  const [error, setError] = useState(null) // { title, message, retry?, tone? }
  const [jobId, setJobId] = useState(null)
  const { job, error: pollError, resume } = useJob(jobId)
  const { videoRef, playRange, activeIndex, onSeeking, stop } = useRangePlayback()
  const [vertical, setVertical] = useState(null) // { clip, url, downloadUrl } shown in the phone
  const [exportStatus, setExportStatus] = useState('idle')
  // The last way a job was started, so "Try again" can repeat it (same file, link or sample).
  const lastSubmit = useRef(null)
  // Id of the last job the server said it doesn't have. Compared with jobId, so a late answer about
  // an old job never hides a new one.
  const [missingId, setMissingId] = useState(null)
  const jobMissing = jobId !== null && missingId === jobId

  useEffect(() => {
    setJobMissingHandler(setMissingId)
    return () => setJobMissingHandler(() => {})
  }, [])

  useEffect(() => {
    let cancelled = false
    getConfig()
      .then((c) => !cancelled && setConfig(c))
      .catch((err) => !cancelled && setConfigError(err.message))
    return () => {
      cancelled = true
    }
  }, [configAttempt])

  const hasVideo = Boolean(job && !jobMissing && HAS_VIDEO.includes(job.status))
  const step = currentStep({ hasVideo, vertical, exportStatus })

  async function start(submit, label) {
    lastSubmit.current = { submit, label }
    setError(null)
    setJobId(null)
    setPending(label)
    try {
      const created = await submit()
      setJobId(created.id)
    } catch (err) {
      setError(failure(err, "Couldn't import that video", () => start(submit, label)))
    } finally {
      setPending(null)
      setUploadPct(null)
    }
  }

  function retryLast() {
    if (lastSubmit.current) start(lastSubmit.current.submit, lastSubmit.current.label)
  }

  function handleFile(file) {
    // Checked here too so a huge file fails instantly, not after minutes of uploading.
    if (config && file.size > config.max_upload_mb * 1024 * 1024) {
      setError({
        title: 'That file is too big',
        message: `Videos can be up to ${formatSize(config.max_upload_mb)}. This one is ${formatSize(Math.ceil(file.size / 1024 / 1024))}.`,
      })
      return
    }
    setUploadPct(0)
    start(() => uploadVideo(file, setUploadPct), 'Uploading…')
  }

  // The sample goes straight on to finding clips: one click from nothing to a list of clips.
  function handleSample() {
    start(async () => {
      const created = await startSample()
      await segmentJob(created.id)
      return created
    }, 'Loading the sample…')
  }

  async function findClips() {
    setError(null)
    setPending('Starting…')
    try {
      await segmentJob(job.id)
      resume()
    } catch (err) {
      setError(failure(err, "Couldn't find clips", findClips))
    } finally {
      setPending(null)
    }
  }

  function showVertical(clip, render) {
    stop()
    setVertical({ clip, url: render.video_url, downloadUrl: render.download_url })
    // Park the original on the clip's first frame so the two line up.
    const video = videoRef.current
    if (video) {
      video.currentTime = clip.start
      video.closest('section')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }
  }

  // The edited clip's vertical render is gone, so it can't stay in the phone.
  function handleEdited(clip) {
    if (vertical?.clip.index === clip.index) setVertical(null)
  }

  // A finished render opens only if nothing is showing; it never replaces what the user is watching.
  function handleRendered(clip, render) {
    if (!vertical) showVertical(clip, render)
  }

  function reset() {
    stop()
    setVertical(null)
    setJobId(null)
    setError(null)
    setExportStatus('idle')
    window.scrollTo({ top: 0 })
  }

  const working = pending !== null

  return (
    <div className="page">
      <header className="topbar">
        <Logo />
        <Steps current={step} />
        <div className="topbar-end">
          {jobId && (
            <button type="button" className="secondary" onClick={reset}>
              New video
            </button>
          )}
        </div>
      </header>

      <main className="main">
        {configError && (
          <ErrorNotice
            title="Can't reach FlipClip"
            message={configError}
            onRetry={() => {
              setConfigError(null)
              setConfigAttempt((a) => a + 1)
            }}
          />
        )}

        {!jobId && (
          <div className="import">
            <h1>Import a video</h1>
            <p className="lede">FlipClip cuts it into short clips and reframes each one to vertical 9:16.</p>
            {error && <ErrorNotice title={error.title} message={error.message} tone={error.tone} onRetry={error.retry} />}
            {working && (
              <div className="status">
                {uploadPct !== null ? (
                  <ProgressBar label={uploadPct < 100 ? 'Uploading…' : 'Checking video…'} value={uploadPct} />
                ) : (
                  <Working>{pending}</Working>
                )}
              </div>
            )}
            <VideoInput
              limits={config}
              onFile={handleFile}
              onUrl={(url) => start(() => submitYoutube(url), 'Checking link…')}
              onSample={handleSample}
              disabled={working}
            />
          </div>
        )}

        {jobMissing && <ErrorNotice title="Video not found" message={JOB_MISSING} onRetry={reset} retryLabel="Start again" />}
        {jobId && !jobMissing && !job && !pollError && (
          <div className="status">
            <Working>Opening video…</Working>
          </div>
        )}
        {job && !jobMissing && !hasVideo && (
          <JobStatus job={job} onRetry={lastSubmit.current ? retryLast : undefined} onStartOver={reset} />
        )}
        {pollError && !jobMissing && (
          <ErrorNotice title="Lost connection to FlipClip" message={pollError} onRetry={resume}>
            <button type="button" className="secondary" onClick={reset}>
              Start over
            </button>
          </ErrorNotice>
        )}

        {hasVideo && (
          <>
            <Preview
              job={job}
              videoRef={videoRef}
              onSeeking={onSeeking}
              // Paused by hand: the clip isn't playing any more, so nothing should say "Stop".
              onPause={stop}
              // The <video> can't read the 404 itself; re-polling the job finds out whether it's gone.
              onSourceError={resume}
              vertical={vertical}
              showPhone={job.status === 'segmented'}
              onPlayRange={playRange}
              onCloseVertical={() => setVertical(null)}
            />

            {job.status === 'ready' &&
              (job.error || error ? (
                <ErrorNotice
                  title={error?.tone === 'busy' ? BUSY_TITLE : "Couldn't find clips"}
                  message={error?.message ?? job.error}
                  tone={error?.tone}
                  onRetry={findClips}
                  retryLabel={working ? 'Starting…' : 'Try again'}
                />
              ) : (
                <section className="timeline timeline--empty" aria-labelledby="next-title">
                  <div>
                    <h2 id="next-title" className="next-title">
                      Video imported
                    </h2>
                    <p className="meta">Next, FlipClip splits it into clips at its scene cuts.</p>
                  </div>
                  <button type="button" onClick={findClips} disabled={working}>
                    {working ? 'Starting…' : 'Find clips'}
                  </button>
                </section>
              ))}

            {job.status === 'segmenting' && (
              <>
                <section className="timeline timeline--empty" aria-label="Finding clips">
                  <ProgressBar label="Finding clips…" value={job.progress} />
                </section>
                <ClipSkeletons label="Finding clips…" />
              </>
            )}

            {job.status === 'segmented' && (
              <ClipWorkspace
                key={job.id}
                jobId={job.id}
                duration={job.duration}
                limits={config}
                videoRef={videoRef}
                playingIndex={activeIndex}
                showingIndex={vertical?.clip.index}
                onPlay={playRange}
                onStop={stop}
                onShowVertical={showVertical}
                onRendered={handleRendered}
                onEdited={handleEdited}
                onExportStatus={setExportStatus}
                onStartOver={reset}
              />
            )}
          </>
        )}
      </main>

      <footer className="footer">
        <span>
          Built by <a href="https://github.com/Robin-Hmaidan">Robin Hmaidan</a>
        </span>
        <span>Videos are deleted from the server after 2 hours.</span>
      </footer>
    </div>
  )
}
