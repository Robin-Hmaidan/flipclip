import { useEffect, useState } from 'react'
import { getJob } from './api.js'

const POLL_MS = 1000
const DONE = ['ready', 'failed']

// Polls a job once a second until it is ready or failed.
export function useJob(jobId) {
  const [job, setJob] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!jobId) return undefined
    let cancelled = false
    let timer

    async function tick() {
      try {
        const next = await getJob(jobId)
        if (cancelled) return
        setJob(next)
        if (!DONE.includes(next.status)) timer = setTimeout(tick, POLL_MS)
      } catch (err) {
        if (!cancelled) setError(err.message)
      }
    }

    tick()
    // Stops polling when the job changes or the user starts over.
    return () => {
      cancelled = true
      clearTimeout(timer)
      setJob(null)
      setError(null)
    }
  }, [jobId])

  return { job, error }
}
