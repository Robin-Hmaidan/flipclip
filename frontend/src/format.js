// Editor timecode, to the tenth of a second: 83.44 -> "00:01:23.4", 3725.25 -> "01:02:05.3".
// Without tenths, for ruler labels: 90 -> "00:01:30".
export function formatTimecode(seconds, tenths = true) {
  const t = Math.round(seconds * 10)
  const h = String(Math.floor(t / 36000)).padStart(2, '0')
  const m = String(Math.floor((t % 36000) / 600)).padStart(2, '0')
  const s = (t % 600) / 10
  return `${h}:${m}:${tenths ? s.toFixed(1).padStart(4, '0') : String(Math.floor(s)).padStart(2, '0')}`
}

// A clip's length in plain seconds: 55.24 -> "55.2 s"
export const formatSeconds = (seconds) => `${seconds.toFixed(1)} s`

// Clip numbers as an editor shows them: 0 -> "01"
export const clipNumber = (index) => String(index + 1).padStart(2, '0')

// Upload and length limits in plain words: 500 -> "500 MB", 2048 -> "2 GB"; 3600 -> "60 minutes".
export function formatSize(mb) {
  return mb >= 1024 && mb % 1024 === 0 ? `${mb / 1024} GB` : `${mb} MB`
}

export function formatLength(seconds) {
  const minutes = Math.round(seconds / 60)
  if (minutes >= 120 && minutes % 60 === 0) return `${minutes / 60} hours`
  return minutes === 1 ? '1 minute' : `${minutes} minutes`
}
