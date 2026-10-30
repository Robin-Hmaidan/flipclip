import { useCallback, useEffect, useState } from 'react'
import { getJob } from './api.js'

const POLL_MS = 1000
// Statuses where nothing changes until the user acts.
const SETTLED = ['ready', 'failed', 'segmented']

// Polls a job once a second until it settles. Call resume() after starting new work on it.
export function useJob(jobId) {
  // Tagged with the job id, so a stale result never shows for a different job.
  const [state, setState] = useState({ id: null, job: null, error: null })
  const [generation, setGeneration] = useState(0)

  useEffect(() => {
    if (!jobId) return undefined
    let cancelled = false
    let timer

    async function tick() {
      try {
        const next = await getJob(jobId)
        if (cancelled) return
        setState({ id: jobId, job: next, error: null })
        if (!SETTLED.includes(next.status)) timer = setTimeout(tick, POLL_MS)
      } catch (err) {
        if (!cancelled) setState((prev) => ({ ...prev, id: jobId, error: err.message }))
      }
    }

    tick()
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [jobId, generation])

  const resume = useCallback(() => setGeneration((g) => g + 1), [])
  const current = state.id === jobId ? state : { job: null, error: null }
  return { job: current.job, error: current.error, resume }
}
