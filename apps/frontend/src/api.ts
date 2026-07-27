import type {
  AssignmentPayload,
  AssignmentsPage,
  AssignmentSummary,
  City,
  CatalogImport,
  CatalogImportReport,
  CityDetail,
  CreateGeozonePayload,
  CreateRunResult,
  Geozone,
  OverlayPayload,
  PaginatedAdStructures,
  PipelineRun,
  Playback,
  Assignment,
  RouteSummary,
  RunObjects,
  RunsPage,
  RunSummary,
  RunTimeline,
  ShootingPayload,
  UpdateGeozonePayload,
  User,
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

export interface CreateRunOptions {
  /** null — «Без задания»: видео вне города и маршрута. */
  assignmentId?: string | null
  operatorUserId?: string | null
}

export function createRun(
  file: File,
  { assignmentId = null, operatorUserId = null }: CreateRunOptions = {},
): Promise<CreateRunResult> {
  return apiFetch('/runs', {
    method: 'POST',
    body: JSON.stringify({
      file_name: file.name,
      content_type: file.type || 'application/octet-stream',
      size_bytes: file.size,
      assignment_id: assignmentId,
      // Время съёмки берём из метаданных файла. Это подсказка, а не истина:
      // копия с карты памяти принесёт время копирования — поэтому правится.
      shot_started_at: new Date(file.lastModified).toISOString(),
      operator_user_id: operatorUserId,
    }),
  })
}

export function updateShooting(
  runId: string,
  payload: ShootingPayload,
): Promise<PipelineRun> {
  return apiFetch(`/runs/${runId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
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
  assignmentId?: string
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
  if (params.assignmentId) query.set('assignment_id', params.assignmentId)
  if (params.assigned !== undefined) query.set('assigned', String(params.assigned))
  return apiFetch(`/runs?${query.toString()}`)
}

export function getUsers(): Promise<User[]> {
  return apiFetch('/users')
}

export function createUser(fullName: string): Promise<User> {
  return apiFetch('/users', {
    method: 'POST',
    body: JSON.stringify({ full_name: fullName }),
  })
}

export function getCities(): Promise<City[]> {
  return apiFetch('/cities')
}

export function getCity(citySlug: string): Promise<CityDetail> {
  return apiFetch(`/cities/${citySlug}`)
}

export function getRouteAssignments(
  citySlug: string,
  routeSlug: string,
): Promise<AssignmentsPage> {
  return apiFetch(`/cities/${citySlug}/routes/${routeSlug}/assignments?page=1&page_size=50`)
}

export function createAssignment(
  citySlug: string,
  routeSlug: string,
  payload: AssignmentPayload = {},
): Promise<Assignment> {
  return apiFetch(`/cities/${citySlug}/routes/${routeSlug}/assignments`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateAssignment(
  assignmentId: string,
  payload: AssignmentPayload,
): Promise<Assignment> {
  return apiFetch(`/assignments/${assignmentId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function getAssignment(assignmentId: string): Promise<Assignment> {
  return apiFetch(`/assignments/${assignmentId}`)
}

export function getAssignmentRuns(assignmentId: string): Promise<PipelineRun[]> {
  return apiFetch(`/assignments/${assignmentId}/runs`)
}

export function getAssignmentSummary(assignmentId: string): Promise<AssignmentSummary> {
  return apiFetch(`/assignments/${assignmentId}/summary`)
}

export function getRouteSummary(
  citySlug: string,
  routeSlug: string,
): Promise<RouteSummary> {
  return apiFetch(`/cities/${citySlug}/routes/${routeSlug}/summary`)
}

export function getRouteGeozones(
  citySlug: string,
  routeSlug: string,
): Promise<Geozone[]> {
  return apiFetch(`/cities/${citySlug}/routes/${routeSlug}/geozones`)
}

export function createGeozone(
  citySlug: string,
  routeSlug: string,
  payload: CreateGeozonePayload,
): Promise<Geozone> {
  return apiFetch(`/cities/${citySlug}/routes/${routeSlug}/geozones`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateGeozone(
  geozoneId: string,
  payload: UpdateGeozonePayload,
): Promise<Geozone> {
  return apiFetch(`/geozones/${geozoneId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function deleteGeozone(geozoneId: string): Promise<void> {
  // DELETE отдаёт 204 без тела — apiFetch ждёт конверт, поэтому отдельно.
  const response = await fetch(`${API_BASE}/geozones/${geozoneId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `HTTP ${response.status}`)
  }
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

export function getAdStructures(
  citySlug: string,
  params: { search?: string; page?: number; pageSize?: number } = {},
): Promise<PaginatedAdStructures> {
  const query = new URLSearchParams()
  if (params.search) query.set('search', params.search)
  query.set('page', String(params.page ?? 1))
  query.set('page_size', String(params.pageSize ?? 500))
  return apiFetch(`/cities/${citySlug}/ad-structures?${query}`)
}

export function getCatalogImports(citySlug: string): Promise<CatalogImport[]> {
  return apiFetch(`/cities/${citySlug}/catalog/imports`)
}

export async function uploadCatalogImport(
  citySlug: string,
  files: File[],
  uploadedByUserId: string,
): Promise<CatalogImportReport> {
  // Форма, а не JSON: файлы идут прямо в бэкенд и там же разбираются.
  // Content-Type не ставим руками — браузер сам допишет boundary.
  const form = new FormData()
  files.forEach((file) => form.append('files', file))
  form.append('uploaded_by_user_id', uploadedByUserId)

  const response = await fetch(`${API_BASE}/cities/${citySlug}/catalog/imports`, {
    method: 'POST',
    body: form,
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    throw new Error(body?.detail ?? `HTTP ${response.status}`)
  }
  return body.data as CatalogImportReport
}

export function applyCatalogImport(importId: string): Promise<CatalogImport> {
  return apiFetch(`/catalog/imports/${importId}/apply`, { method: 'POST' })
}

export function restoreCatalogImport(importId: string): Promise<CatalogImport> {
  return apiFetch(`/catalog/imports/${importId}/restore`, { method: 'POST' })
}

export async function deleteCatalogImport(importId: string): Promise<void> {
  // DELETE отдаёт 204 без тела — apiFetch ждёт конверт, поэтому отдельно.
  const response = await fetch(`${API_BASE}/catalog/imports/${importId}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `HTTP ${response.status}`)
  }
}
