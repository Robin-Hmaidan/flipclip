import { useEffect } from 'react'
import { useExport } from '../useExport.js'
import { ProgressBar } from './JobStatus.jsx'

// A click on a temporary link: the server sends the zip as an attachment, so the page stays put.
function download(url) {
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.append(a)
  a.click()
  a.remove()
}

// onStatus reports idle/rendering/zipping/done/failed, for the step bar.
export default function ExportPanel({ jobId, count, refreshKey, onStarted, onStatus }) {
  const exp = useExport(jobId, { onStarted, onReady: download, refreshKey })

  useEffect(() => {
    onStatus?.(exp.status)
  }, [exp.status, onStatus])

  return (
    <section className="export" aria-labelledby="export-title">
      <div className="panel-head">
        <h2 id="export-title" className="label">
          Export
        </h2>
      </div>
      <div className="export-body">
        <p className="meta">
          All {count} {count === 1 ? 'clip' : 'clips'} as vertical videos in one .zip file. Clips that aren't vertical yet
          are made vertical first.
        </p>
        <div className="export-action">
          {exp.status === 'idle' && (
            <button type="button" onClick={exp.start}>
              Download all (.zip)
            </button>
          )}
          {exp.busy && (
            <ProgressBar label={exp.status === 'zipping' ? 'Zipping…' : 'Making clips vertical…'} value={exp.progress} />
          )}
          {/* Kept after the automatic download, in case the browser blocked it or it needs saving again. */}
          {exp.status === 'done' && (
            <a className="button" href={exp.download_url} download>
              Download .zip
            </a>
          )}
          {exp.status === 'failed' && (
            <>
              <p className="problem" role="alert">
                {exp.error || "The export didn't finish."}
              </p>
              <button type="button" onClick={exp.start}>
                Try again
              </button>
            </>
          )}
        </div>
      </div>
    </section>
  )
}
