import { useCallback, useEffect, useRef, useState } from 'react'

// Plays one [start, end] range of a <video>, then pauses.
export function useRangePlayback() {
  const videoRef = useRef(null)
  const range = useRef(null)
  const frame = useRef(0)
  const [activeIndex, setActiveIndex] = useState(null)

  const stop = useCallback(() => {
    range.current = null
    cancelAnimationFrame(frame.current)
    setActiveIndex(null)
  }, [])

  const playRange = useCallback(
    (clip) => {
      const video = videoRef.current
      if (!video) return
      cancelAnimationFrame(frame.current)
      range.current = clip
      setActiveIndex(clip.index)
      video.currentTime = clip.start
      video.play().catch(() => {}) // autoplay can be blocked; the seek still happened
      // On phones the list sits below the video; bring the player back into view.
      video.scrollIntoView({ behavior: 'smooth', block: 'nearest' })

      // Checked every animation frame: timeupdate fires only ~4x/s and would overshoot the end.
      frame.current = requestAnimationFrame(function watch() {
        if (range.current !== clip) return
        if (video.currentTime >= clip.end) {
          video.pause()
          stop()
          return
        }
        frame.current = requestAnimationFrame(watch)
      })
    },
    [stop],
  )

  // If the user seeks outside the clip, they've left it: stop enforcing the range.
  const onSeeking = useCallback(() => {
    const video = videoRef.current
    const r = range.current
    if (r && (video.currentTime < r.start - 0.5 || video.currentTime > r.end)) stop()
  }, [stop])

  useEffect(() => () => cancelAnimationFrame(frame.current), [])

  return { videoRef, playRange, activeIndex, onSeeking, stop }
}
