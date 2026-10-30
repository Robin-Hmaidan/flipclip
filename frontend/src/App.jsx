import { useEffect, useState } from 'react'

export default function App() {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('/api/health')
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then(setHealth)
      .catch((err) => setError(err.message))
  }, [])

  return (
    <main className="app">
      <h1>FlipClip</h1>
      <p className="tagline">Turn horizontal videos into vertical clips.</p>
      <section className="status">
        {error && <p className="status-error">Backend unreachable: {error}</p>}
        {!error && !health && <p>Checking backend…</p>}
        {health && (
          <p>
            Backend: <strong>{health.status}</strong> · ffmpeg{' '}
            <strong>{health.ffmpeg_version ?? 'not found'}</strong>
          </p>
        )}
      </section>
    </main>
  )
}
