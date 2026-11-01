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

export default function ExportPanel({ jobId, onStarted }) {
  const exp = useExport(jobId, { onStarted, onReady: download })

  return (
    <div className="export">
      {(exp.status === 'idle' || exp.status === 'failed') && (
        <button type="button" onClick={exp.start}>
          Export all (zip)
        </button>
      )}
      {exp.busy && (
        <ProgressBar label={exp.status === 'zipping' ? 'Zipping…' : 'Rendering clips…'} value={exp.progress} />
      )}
      {/* Kept after the automatic download, in case the browser blocked it or it needs saving again. */}
      {exp.status === 'done' && (
        <a className="button" href={exp.download_url} download>
          Download zip
        </a>
      )}
      {exp.status === 'failed' && (
        <p className="export-error" role="alert">
          {exp.error}
        </p>
      )}
    </div>
  )
}
