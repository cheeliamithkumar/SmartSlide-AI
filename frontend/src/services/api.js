import axios from 'axios'

const baseURL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '') + '/api'

export const http = axios.create({ baseURL, timeout: 120000 })

/** Convert any axios error into a friendly message. */
export function errorMessage(err, fallback = 'Something went wrong. Please try again.') {
  if (!err) return fallback
  if (err.response) {
    const d = err.response.data
    if (d && typeof d.detail === 'string') return d.detail
    if (err.response.status === 413) return 'The file is too large.'
    if (err.response.status >= 500) return 'The server encountered an error. Please try again.'
    return fallback
  }
  if (err.code === 'ECONNABORTED') return 'The request timed out. Please try again.'
  if (err.message === 'Network Error') return 'Cannot reach the SmartSlide AI server. Is the backend running?'
  return err.message || fallback
}

export const api = {
  health: () => http.get('/health').then((r) => r.data),
  templates: () => http.get('/templates').then((r) => r.data),

  uploadDocument: (file, onProgress) => {
    const form = new FormData()
    form.append('file', file)
    return http
      .post('/documents', form, {
        onUploadProgress: (e) => e.total && onProgress?.(Math.round((e.loaded / e.total) * 100)),
      })
      .then((r) => r.data)
  },
  getDocument: (id) => http.get(`/documents/${id}`).then((r) => r.data),
  getContent: (id) => http.get(`/documents/${id}/content`).then((r) => r.data),

  // On serverless hosting the conversion runs inside this request, so allow it plenty of time.
  createJob: (payload) => http.post('/jobs', payload, { timeout: 310000 }).then((r) => r.data),
  getJob: (id) => http.get(`/jobs/${id}`).then((r) => r.data),

  getPresentation: (id) => http.get(`/presentations/${id}`).then((r) => r.data),
  updatePresentation: (id, payload) => http.patch(`/presentations/${id}`, payload).then((r) => r.data),
  updateSlide: (id, slideId, payload) =>
    http.patch(`/presentations/${id}/slides/${slideId}`, payload).then((r) => r.data),
  deleteSlide: (id, slideId) => http.delete(`/presentations/${id}/slides/${slideId}`).then((r) => r.data),
  reorderSlides: (id, order) => http.put(`/presentations/${id}/slides/order`, { order }).then((r) => r.data),
  addSlide: (id, slide, after) =>
    http.post(`/presentations/${id}/slides`, slide, { params: after ? { after } : {} }).then((r) => r.data),
  regenerateSlide: (id, slideId) =>
    http.post(`/presentations/${id}/slides/${slideId}/regenerate`).then((r) => r.data),

  /** Download the PPTX (rendered with the latest edits) and save it in the browser. */
  downloadPresentation: async (id) => {
    const res = await http.get(`/presentations/${id}/download`, { responseType: 'blob' })
    const cd = res.headers['content-disposition'] || ''
    const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd)
    const name = match ? decodeURIComponent(match[1]) : 'presentation.pptx'
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    document.body.appendChild(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 2000)
    return name
  },
}
