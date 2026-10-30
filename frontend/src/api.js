// FastAPI sends {detail: string} for our errors and {detail: [...]} for validation errors.
function errorMessage(body, status) {
  return typeof body?.detail === 'string' ? body.detail : `Request failed (HTTP ${status}).`
}

async function request(path, options) {
  const res = await fetch(path, options)
  const body = await res.json().catch(() => null)
  if (!res.ok) throw new Error(errorMessage(body, res.status))
  return body
}

export const getHealth = () => request('/api/health')
export const getConfig = () => request('/api/config')
export const getJob = (id) => request(`/api/jobs/${encodeURIComponent(id)}`)
export const getClips = (id) => request(`/api/jobs/${encodeURIComponent(id)}/clips`)
export const segmentJob = (id) =>
  request(`/api/jobs/${encodeURIComponent(id)}/segment`, { method: 'POST' })

export const submitYoutube = (url) =>
  request('/api/jobs/youtube', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })

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
      else reject(new Error(errorMessage(xhr.response, xhr.status)))
    }
    xhr.onerror = () => reject(new Error('Upload failed. Check your connection and try again.'))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}
