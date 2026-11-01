import { useCallback, useEffect, useRef, useState } from 'react'
import { getExport, startExport } from './api.js'

const POLL_MS = 1000
const IDLE = { status: 'idle', progress: 0, error: null, download_url: null }
const ACTIVE = ['rendering', 'zipping']

// Export state for a job: start() renders whatever is missing and zips it all, then polls until
// done or failed. onStarted runs once the server has queued the work; onReady gets the zip URL.
export function useExport(jobId, { onStarted, onReady }) {
  const [state, setState] = useState(IDLE)
  const [polling, setPolling] = useState(false)
  const callbacks = useRef({ onStarted, onReady })
  useEffect(() => {
    callbacks.current = { onStarted, onReady }
  })

  useEffect(() => {
    if (!polling) return undefined
    let cancelled = false
    let timer

    async function tick() {
      try {
        const next = await getExport(jobId)
        if (cancelled) return
        setState(next)
        if (ACTIVE.includes(next.status)) {
          timer = setTimeout(tick, POLL_MS)
          return
        }
        setPolling(false)
        if (next.status === 'done') callbacks.current.onReady?.(next.download_url)
      } catch (err) {
        if (cancelled) return
        setState((prev) => ({ ...prev, status: 'failed', error: err.message }))
        setPolling(false)
      }
    }

    timer = setTimeout(tick, POLL_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [jobId, polling])

  const start = useCallback(async () => {
    setState((prev) => ({ ...prev, status: 'rendering', progress: 0, error: null }))
    try {
      const next = await startExport(jobId)
      setState(next)
      callbacks.current.onStarted?.()
      if (next.status === 'done') callbacks.current.onReady?.(next.download_url)
      else setPolling(true)
    } catch (err) {
      setState((prev) => ({ ...prev, status: 'failed', error: err.message }))
    }
  }, [jobId])

  return { ...state, busy: ACTIVE.includes(state.status), start }
}
