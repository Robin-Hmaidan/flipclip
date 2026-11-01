import { useEffect, useRef, useState } from 'react'
import { getConfig, isBusy, segmentJob, startSample, submitYoutube, uploadVideo } from './api.js'
import ClipList, { ClipSkeletons } from './components/ClipList.jsx'
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
function currentStep({ hasVideo, vertical, exportStatus, editing }) {
  if (editing) return 'edit'
  if (exportStatus !== 'idle') return 'export'
  if (vertical) return 'edit'
  return hasVideo ? 'clips' : 'input'
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
  const [vertical, setVertical] = useState(null) // { clip, url, downloadUrl } shown next to the original
  const [editing, setEditing] = useState(false)
  const [exportStatus, setExportStatus] = useState('idle')
  // The last way a job was started, so "Try again" can repeat it (same file, link or sample).
  const lastSubmit = useRef(null)

  useEffect(() => {
    let cancelled = false
    getConfig()
      .then((c) => !cancelled && setConfig(c))
      .catch((err) => !cancelled && setConfigError(err.message))
    return () => {
      cancelled = true
    }
  }, [configAttempt])

  const hasVideo = Boolean(job && HAS_VIDEO.includes(job.status))
  const step = currentStep({ hasVideo, vertical, exportStatus, editing })

  async function start(submit, label) {
    lastSubmit.current = { submit, label }
    setError(null)
    setJobId(null)
    setPending(label)
    try {
      const created = await submit()
      setJobId(created.id)
    } catch (err) {
      setError(failure(err, "We couldn't start with that video", () => start(submit, label)))
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
    }, 'Preparing the sample…')
  }

  async function findClips() {
    setError(null)
    setPending('Starting…')
    try {
      await segmentJob(job.id)
      resume()
    } catch (err) {
      setError(failure(err, "We couldn't start finding clips", findClips))
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

  // The editor has its own player; the main one shouldn't keep playing underneath it.
  function openEditor() {
    stop()
    videoRef.current?.pause()
    setEditing(true)
  }

  // The edited clip's vertical render is gone, so it can't stay open.
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
    setEditing(false)
    setExportStatus('idle')
    window.scrollTo({ top: 0 })
  }

  const working = pending !== null

  return (
    <div className="page">
      <header className="topbar">
        <div className="brand">
          <Logo />
          <div>
            <p className="brand-name">FlipClip</p>
            <p className="brand-tagline">Long videos in, vertical clips out</p>
          </div>
        </div>
        {jobId && (
          <button type="button" className="secondary" onClick={reset}>
            New video
          </button>
        )}
      </header>

      <main className="app">
        <Steps current={step} />

        {configError && (
          <ErrorNotice
            title="Can't reach FlipClip right now"
            message={configError}
            onRetry={() => {
              setConfigError(null)
              setConfigAttempt((a) => a + 1)
            }}
          />
        )}

        {!jobId && (
          <>
            <div className="intro">
              <h1>Turn a long video into vertical clips</h1>
              <p>
                FlipClip finds the best cuts, then crops each clip to 9:16 and keeps the speaker in frame. Ready for
                Shorts, Reels and TikTok.
              </p>
            </div>
            {error && <ErrorNotice title={error.title} message={error.message} tone={error.tone} onRetry={error.retry} />}
            {working && (
              <div className="card">
                {uploadPct !== null ? (
                  <ProgressBar label={uploadPct < 100 ? 'Uploading…' : 'Checking video…'} value={uploadPct} />
                ) : (
                  <p className="working">
                    <span className="spinner" aria-hidden="true" />
                    {pending}
                  </p>
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
          </>
        )}

        {jobId && !job && !pollError && (
          <div className="card">
            <p className="working">
              <span className="spinner" aria-hidden="true" />
              Loading your video…
            </p>
          </div>
        )}
        {job && !hasVideo && <JobStatus job={job} onRetry={lastSubmit.current ? retryLast : undefined} onStartOver={reset} />}
        {pollError && (
          <ErrorNotice title="Lost touch with FlipClip" message={pollError} onRetry={resume}>
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
              vertical={vertical}
              showPlaceholder={job.status === 'segmented'}
              onPlayRange={playRange}
              onCloseVertical={() => setVertical(null)}
            />

            {job.status === 'ready' &&
              (job.error || error ? (
                <ErrorNotice
                  title={error?.tone === 'busy' ? BUSY_TITLE : "We couldn't find clips"}
                  message={error?.message ?? job.error}
                  tone={error?.tone}
                  onRetry={findClips}
                  retryLabel={working ? 'Starting…' : 'Try again'}
                />
              ) : (
                <div className="card next">
                  <div>
                    <p className="next-title">Video ready</p>
                    <p className="section-meta">Next, FlipClip splits it into clips at its scene cuts.</p>
                  </div>
                  <button type="button" onClick={findClips} disabled={working}>
                    {working ? 'Starting…' : 'Find clips'}
                  </button>
                </div>
              ))}

            {job.status === 'segmenting' && (
              <>
                <div className="card">
                  <ProgressBar label="Finding clips…" value={job.progress} />
                </div>
                <ClipSkeletons label="Finding clips…" />
              </>
            )}

            {job.status === 'segmented' && (
              <ClipList
                key={job.id}
                jobId={job.id}
                duration={job.duration}
                limits={config}
                playingIndex={activeIndex}
                showingIndex={vertical?.clip.index}
                onPlay={playRange}
                onShowVertical={showVertical}
                onRendered={handleRendered}
                onEditOpen={openEditor}
                onEditClose={() => setEditing(false)}
                onEdited={handleEdited}
                onExportStatus={setExportStatus}
                onStartOver={reset}
              />
            )}
          </>
        )}
      </main>

      <footer className="footer">
        <h2>How it works</h2>
        <ol>
          <li>Add a video: upload a file, paste a YouTube link or try the sample.</li>
          <li>
            FlipClip splits it at its scene cuts into clips of up to {config?.max_clip_sec ?? 60} seconds.
          </li>
          <li>Each clip is cropped to 9:16 following the speaker's face. Edit, then download.</li>
        </ol>
        <p className="footer-note">Videos are deleted from the server after 2 hours.</p>
      </footer>
    </div>
  )
}
