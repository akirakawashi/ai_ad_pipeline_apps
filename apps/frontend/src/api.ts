import type {
  CreateRunResult,
  OverlayPayload,
  PipelineRun,
  Playback,
  RunObjects,
  RunsPage,
  RunSummary,
  RunTimeline,
} from './types'

const API_BASE =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000/api/v1'

interface ApiEnvelope<T> {
  data: T
}

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `HTTP ${response.status}`)
  }
  const envelope = (await response.json()) as ApiEnvelope<T>
  return envelope.data
}

export function createRun(file: File): Promise<CreateRunResult> {
  return apiFetch('/runs', {
    method: 'POST',
    body: JSON.stringify({
      file_name: file.name,
      content_type: file.type || 'application/octet-stream',
      size_bytes: file.size,
    }),
  })
}

export function uploadVideo(
  target: CreateRunResult['upload'],
  file: File,
  onProgress: (progress: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open(target.method, target.url)
    Object.entries(target.headers).forEach(([name, value]) => {
      request.setRequestHeader(name, value)
    })
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        onProgress(Math.round((event.loaded / event.total) * 100))
      }
    }
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        onProgress(100)
        resolve()
      } else {
        reject(new Error(`Upload failed: HTTP ${request.status}`))
      }
    }
    request.onerror = () => reject(new Error('Upload connection failed'))
    request.send(file)
  })
}

export function completeUpload(runId: string): Promise<PipelineRun> {
  return apiFetch(`/runs/${runId}/upload-complete`, {
    method: 'POST',
  })
}

export function listRuns(page = 1): Promise<RunsPage> {
  return apiFetch(`/runs?page=${page}&page_size=20`)
}

export function getRun(runId: string): Promise<PipelineRun> {
  return apiFetch(`/runs/${runId}`)
}

export function getRunSummary(runId: string): Promise<RunSummary> {
  return apiFetch(`/runs/${runId}/summary`)
}

export function getRunObjects(runId: string): Promise<RunObjects> {
  return apiFetch(`/runs/${runId}/objects?limit=100`)
}

export function getRunTimeline(runId: string): Promise<RunTimeline> {
  return apiFetch(`/runs/${runId}/timeline?bucket_seconds=5`)
}

export function getRunPlayback(runId: string): Promise<Playback> {
  return apiFetch(`/runs/${runId}/playback`)
}

export function getRunOverlay(runId: string): Promise<OverlayPayload> {
  return apiFetch(`/runs/${runId}/overlay`)
}
