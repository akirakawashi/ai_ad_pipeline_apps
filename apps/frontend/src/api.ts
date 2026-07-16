import type {
  BatchesPage,
  BatchSummary,
  City,
  CityDetail,
  CreateRunResult,
  OverlayPayload,
  PipelineRun,
  Playback,
  RouteBatch,
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

/** batchId === null — «Без маршрута»: видео вне города и маршрута. */
export function createRun(
  file: File,
  batchId: string | null = null,
): Promise<CreateRunResult> {
  return apiFetch('/runs', {
    method: 'POST',
    body: JSON.stringify({
      file_name: file.name,
      content_type: file.type || 'application/octet-stream',
      size_bytes: file.size,
      batch_id: batchId,
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
        reject(new Error('Не удалось загрузить видео. Попробуйте ещё раз.'))
      }
    }
    request.onerror = () =>
      reject(new Error('Связь оборвалась во время загрузки видео.'))
    request.send(file)
  })
}

export function completeUpload(runId: string): Promise<PipelineRun> {
  return apiFetch(`/runs/${runId}/upload-complete`, {
    method: 'POST',
  })
}

export interface ListRunsParams {
  page?: number
  pageSize?: number
  status?: string
  cityId?: string
  routeId?: string
  batchId?: string
  /** false — только видео без маршрута. */
  assigned?: boolean
}

export function listRuns(params: ListRunsParams = {}): Promise<RunsPage> {
  const query = new URLSearchParams()
  query.set('page', String(params.page ?? 1))
  query.set('page_size', String(params.pageSize ?? 20))
  if (params.status) query.set('status', params.status)
  if (params.cityId) query.set('city_id', params.cityId)
  if (params.routeId) query.set('route_id', params.routeId)
  if (params.batchId) query.set('batch_id', params.batchId)
  if (params.assigned !== undefined) query.set('assigned', String(params.assigned))
  return apiFetch(`/runs?${query.toString()}`)
}

export function getCities(): Promise<City[]> {
  return apiFetch('/cities')
}

export function getCity(citySlug: string): Promise<CityDetail> {
  return apiFetch(`/cities/${citySlug}`)
}

export function getRouteBatches(
  citySlug: string,
  routeSlug: string,
): Promise<BatchesPage> {
  return apiFetch(`/cities/${citySlug}/routes/${routeSlug}/batches?page=1&page_size=50`)
}

export function createBatch(
  citySlug: string,
  routeSlug: string,
): Promise<RouteBatch> {
  return apiFetch(`/cities/${citySlug}/routes/${routeSlug}/batches`, {
    method: 'POST',
    body: '{}',
  })
}

export function getBatch(batchId: string): Promise<RouteBatch> {
  return apiFetch(`/batches/${batchId}`)
}

export function getBatchRuns(batchId: string): Promise<PipelineRun[]> {
  return apiFetch(`/batches/${batchId}/runs`)
}

export function getBatchSummary(batchId: string): Promise<BatchSummary> {
  return apiFetch(`/batches/${batchId}/summary`)
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
