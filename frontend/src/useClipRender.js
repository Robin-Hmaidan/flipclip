import { useCallback, useEffect, useRef, useState } from 'react'
import { getClipRender, renderClip } from './api.js'

const POLL_MS = 1000
const IDLE = { status: 'idle', progress: 0, error: null, video_url: null }

// Render state for one clip: start() queues the render, then polls until done or failed.
// A new syncKey re-reads the state from the server, for renders something else started (an export).
export function useClipRender(jobId, index, onDone, syncKey) {
  const [state, setState] = useState(IDLE)
  const [polling, setPolling] = useState(false)
  // Latest callback without restarting the polling effect when the parent re-renders.
  const onDoneRef = useRef(onDone)
  useEffect(() => {
    onDoneRef.current = onDone
  })
  // onDone is for renders the user asked for; one an export started finishes quietly.
  const requestedRef = useRef(false)

  useEffect(() => {
    if (!polling) return undefined
    let cancelled = false
    let timer

    async function tick() {
      try {
        const next = await getClipRender(jobId, index)
        if (cancelled) return
        setState(next)
        if (next.status === 'queued' || next.status === 'rendering') {
          timer = setTimeout(tick, POLL_MS)
          return
        }
        setPolling(false)
        if (next.status === 'done' && requestedRef.current) onDoneRef.current?.(next.video_url)
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
  }, [jobId, index, polling])

  useEffect(() => {
    if (!syncKey) return undefined
    let cancelled = false
    getClipRender(jobId, index)
      .then((next) => {
        if (cancelled) return
        setState(next)
        if (next.status === 'queued' || next.status === 'rendering') setPolling(true)
      })
      .catch(() => {}) // the card keeps what it showed; the export reports its own errors
    return () => {
      cancelled = true
    }
  }, [jobId, index, syncKey])

  const start = useCallback(async () => {
    requestedRef.current = true
    setState((prev) => ({ ...prev, status: 'queued', progress: 0, error: null }))
    try {
      const next = await renderClip(jobId, index)
      setState(next)
      if (next.status === 'done') onDoneRef.current?.(next.video_url)
      else setPolling(true)
    } catch (err) {
      setState((prev) => ({ ...prev, status: 'failed', error: err.message }))
    }
  }, [jobId, index])

  return { ...state, start }
}
