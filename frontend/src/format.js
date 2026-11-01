// 75.4 -> "1:15", 3725 -> "1:02:05"
export function formatTime(seconds) {
  const s = Math.round(seconds)
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const rest = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${rest}` : `${m}:${rest}`
}

// To the tenth of a second, for clip bounds: 65.34 -> "01:05.3", 3725.25 -> "1:02:05.3"
export function formatPrecise(seconds) {
  const tenths = Math.round(seconds * 10)
  const h = Math.floor(tenths / 36000)
  const m = String(Math.floor((tenths % 36000) / 600)).padStart(2, '0')
  const s = ((tenths % 600) / 10).toFixed(1).padStart(4, '0')
  return h ? `${h}:${m}:${s}` : `${m}:${s}`
}

// Upload and length limits in plain words: 500 -> "500 MB", 2048 -> "2 GB"; 3600 -> "60 minutes".
export function formatSize(mb) {
  return mb >= 1024 && mb % 1024 === 0 ? `${mb / 1024} GB` : `${mb} MB`
}

export function formatLength(seconds) {
  const minutes = Math.round(seconds / 60)
  if (minutes >= 120 && minutes % 60 === 0) return `${minutes / 60} hours`
  return minutes === 1 ? '1 minute' : `${minutes} minutes`
}
