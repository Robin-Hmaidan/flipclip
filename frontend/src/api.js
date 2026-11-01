const OFFLINE = "Can't reach FlipClip. Check your connection and try again."
const SERVER_FAULT = 'Something went wrong on our side. Please try again.'
// The server answers "not found" both for jobs its 2-hour cleanup removed and for jobs it lost on a
// restart (they live in memory). It can't tell which, so the message mustn't pick one.
export const JOB_MISSING = 'This video is no longer on the server (it expired or the server restarted). Start again.'

// Any request can be the first to find the job gone (polling stops once a job settles), so the app
// registers one handler here rather than every caller checking. It gets the missing job's id.
let jobMissingHandler = () => {}
export function setJobMissingHandler(fn) {
  jobMissingHandler = fn
}

// The status rides along so callers can tell "busy, try again soon" (429) from a real failure.
class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

// The server is at its limit of videos in progress; nothing is wrong with the user's video.
export const isBusy = (err) => err?.status === 429

// FastAPI sends {detail: string} for our errors, which are written for users already.
// Anything else (validation lists, proxy errors, empty bodies) gets a plain-words fallback.
const isJobMissing = (body, status) => status === 404 && body?.detail === 'Job not found.'

function errorMessage(body, status) {
  if (isJobMissing(body, status)) return JOB_MISSING
  if (typeof body?.detail === 'string') return body.detail
  if (status >= 500) return SERVER_FAULT
  return `Something went wrong (error ${status}). Please try again.`
}

async function request(path, options) {
  let res
  try {
    res = await fetch(path, options)
  } catch {
    throw new Error(OFFLINE) // fetch only rejects when no response arrived at all
  }
  const body = await res.json().catch(() => null)
  if (isJobMissing(body, res.status)) {
    const id = path.match(/^\/api\/jobs\/([^/?]+)/)?.[1]
    if (id) jobMissingHandler(decodeURIComponent(id))
  }
  if (!res.ok) throw new ApiError(errorMessage(body, res.status), res.status)
  return body
}

export const getHealth = () => request('/api/health')
export const getConfig = () => request('/api/config')
export const getJob = (id) => request(`/api/jobs/${encodeURIComponent(id)}`)
export const getClips = (id) => request(`/api/jobs/${encodeURIComponent(id)}/clips`)
export const segmentJob = (id) =>
  request(`/api/jobs/${encodeURIComponent(id)}/segment`, { method: 'POST' })

const clipPath = (id, index) => `/api/jobs/${encodeURIComponent(id)}/clips/${index}`
export const getClipRender = (id, index) => request(clipPath(id, index))
export const renderClip = (id, index) => request(`${clipPath(id, index)}/render`, { method: 'POST' })
export const editClip = (id, index, start, end) =>
  request(clipPath(id, index), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start, end }),
  })
export const resetClip = (id, index) => request(`${clipPath(id, index)}/reset`, { method: 'POST' })

const exportPath = (id) => `/api/jobs/${encodeURIComponent(id)}/export`
export const getExport = (id) => request(exportPath(id))
export const startExport = (id) => request(exportPath(id), { method: 'POST' })

export const submitYoutube = (url) =>
  request('/api/jobs/youtube', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })

export const startSample = () => request('/api/jobs/sample', { method: 'POST' })

// XMLHttpRequest rather than fetch: fetch has no upload progress events.
export function uploadVideo(file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/jobs/upload')
    xhr.responseType = 'json'
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response)
      else reject(new ApiError(errorMessage(xhr.response, xhr.status), xhr.status))
    }
    xhr.onerror = () => reject(new Error('Upload failed. Check your connection and try again.'))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}
