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

// onStatus reports idle/rendering/zipping/done/failed, for the step indicator.
export default function ExportPanel({ jobId, refreshKey, onStarted, onStatus }) {
  const exp = useExport(jobId, { onStarted, onReady: download, refreshKey })

  useEffect(() => {
    onStatus?.(exp.status)
  }, [exp.status, onStatus])

  return (
    <div className="export">
      {exp.status === 'idle' && (
        <button type="button" onClick={exp.start}>
          Export all (zip)
        </button>
      )}
      {exp.busy && (
        <ProgressBar label={exp.status === 'zipping' ? 'Zipping…' : 'Making clips vertical…'} value={exp.progress} />
      )}
      {/* Kept after the automatic download, in case the browser blocked it or it needs saving again. */}
      {exp.status === 'done' && (
        <a className="button" href={exp.download_url} download>
          Download zip
        </a>
      )}
      {exp.status === 'failed' && (
        <>
          <p className="export-error" role="alert">
            {exp.error || "The export didn't finish."}
          </p>
          <button type="button" onClick={exp.start}>
            Try again
          </button>
        </>
      )}
    </div>
  )
}
