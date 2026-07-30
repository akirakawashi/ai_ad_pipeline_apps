import type { RoutePeriod } from './routing'
import { isoFromDateInput, isoFromDateInputExclusiveEnd } from './utils/formatters'
import type {
  AssignmentPayload,
  AssignmentsPage,
  AssignmentSummary,
  City,
  CityPayload,
  CityUpdatePayload,
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
  Route,
  RoutePayload,
  RouteSummary,
  RouteUpdatePayload,
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

/**
 * Пароль справочников. Проверяет его бэкенд — здесь только хранение на время
 * вкладки и подстановка заголовка. sessionStorage, а не localStorage: закрыл
 * вкладку — вошёл заново, на общем компьютере это важнее удобства.
 *
 * Настоящая защита в том, что админские эндпоинты отвечают 401 сами. Эта форма
 * лишь избавляет от системного окна браузера.
 */
const ADMIN_STORAGE_KEY = 'admin-basic-auth'

let adminToken: string | null = sessionStorage.getItem(ADMIN_STORAGE_KEY)

function basicToken(login: string, password: string): string {
  // btoa не умеет ничего за пределами latin1, поэтому кодируем сами.
  const bytes = new TextEncoder().encode(`${login}:${password}`)
  return btoa(Array.from(bytes, (byte) => String.fromCharCode(byte)).join(''))
}

function adminHeaders(): Record<string, string> {
  return adminToken ? { Authorization: `Basic ${adminToken}` } : {}
}

export function hasAdminSession(): boolean {
  return adminToken !== null
}

export function forgetAdminSession(): void {
  adminToken = null
  sessionStorage.removeItem(ADMIN_STORAGE_KEY)
}

/** Проверяет пару на бэкенде и запоминает её только если он ответил 204. */
export async function signInAdmin(login: string, password: string): Promise<void> {
  const token = basicToken(login, password)
  const response = await fetch(`${API_BASE}/admin/session`, {
    headers: { Authorization: `Basic ${token}` },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? 'Не удалось войти в справочники.')
  }
  adminToken = token
  sessionStorage.setItem(ADMIN_STORAGE_KEY, token)
}

async function apiFetch<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...adminHeaders(),
      ...options?.headers,
    },
  })
  if (!response.ok) {
    // Пароль сменили или сессию не приняли — форма входа должна вернуться.
    if (response.status === 401) forgetAdminSession()
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.detail ?? `HTTP ${response.status}`)
  }
  const envelope = (await response.json()) as ApiEnvelope<T>
  return envelope.data
}

export interface CreateRunOptions {
  /** Обязательно: съёмка всегда принадлежит заданию, а через него — маршруту. */
  assignmentId: string
  operatorUserId?: string | null
  /**
   * Когда снимали, ISO с зоной. Дату для каждого файла человек обязательно
   * выбирает вручную; метку изменения файла не используем.
   */
  shotStartedAt: string
}

export function createRun(
  file: File,
  { assignmentId, operatorUserId = null, shotStartedAt }: CreateRunOptions,
): Promise<CreateRunResult> {
  return apiFetch('/runs', {
    method: 'POST',
    body: JSON.stringify({
      file_name: file.name,
      content_type: file.type || 'application/octet-stream',
      size_bytes: file.size,
      assignment_id: assignmentId,
      shot_started_at: shotStartedAt,
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
}

export function listRuns(params: ListRunsParams = {}): Promise<RunsPage> {
  const query = new URLSearchParams()
  query.set('page', String(params.page ?? 1))
  query.set('page_size', String(params.pageSize ?? 20))
  if (params.status) query.set('status', params.status)
  if (params.cityId) query.set('city_id', params.cityId)
  if (params.routeId) query.set('route_id', params.routeId)
  if (params.assignmentId) query.set('assignment_id', params.assignmentId)
  return apiFetch(`/runs?${query.toString()}`)
}

/** `includeInactive` — только для админ-панели: обычным экранам скрытые не нужны. */
export function getUsers(includeInactive = false): Promise<User[]> {
  return apiFetch(`/users${includeInactive ? '?include_inactive=true' : ''}`)
}

export function createUser(fullName: string): Promise<User> {
  return apiFetch('/users', {
    method: 'POST',
    body: JSON.stringify({ full_name: fullName }),
  })
}

export interface UserUpdatePayload {
  full_name?: string
  is_active?: boolean
}

export function updateUser(userId: string, payload: UserUpdatePayload): Promise<User> {
  return apiFetch(`/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

/**
 * Список городов. `includeInactive` включают только справочники на /admin:
 * скрытый город обычному пользователю не виден нигде, но вернуть его надо
 * откуда-то — удаления города нет.
 */
export function getCities(includeInactive = false): Promise<City[]> {
  return apiFetch(`/cities${includeInactive ? '?include_inactive=true' : ''}`)
}

/** `includeInactive` здесь про маршруты города — сам город отдаётся и скрытым. */
export function getCity(citySlug: string, includeInactive = false): Promise<CityDetail> {
  const query = includeInactive ? '?include_inactive=true' : ''
  return apiFetch(`/cities/${citySlug}${query}`)
}

// --- справочники городов и маршрутов --------------------------------------

export function createCity(payload: CityPayload): Promise<City> {
  return apiFetch('/cities', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateCity(
  citySlug: string,
  payload: CityUpdatePayload,
): Promise<CityDetail> {
  return apiFetch(`/cities/${citySlug}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function createRoute(
  citySlug: string,
  payload: RoutePayload,
): Promise<Route> {
  return apiFetch(`/cities/${citySlug}/routes`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateRoute(
  citySlug: string,
  routeSlug: string,
  payload: RouteUpdatePayload,
): Promise<Route> {
  return apiFetch(`/cities/${citySlug}/routes/${routeSlug}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

/**
 * Геометрия города и маршрута. Загружается формой (файл идёт прямо в бэкенд и
 * там разбирается), читается обычным GET — бэкенд отдаёт её с ETag, поэтому
 * повторные заходы на карту получают 304 вместо полутора мегабайт.
 */
export function uploadRoadsGeometry(
  citySlug: string,
  file: File,
): Promise<CityDetail> {
  return uploadGeometry(`/cities/${citySlug}/roads-geometry`, file)
}

/**
 * Отправляет нарисованную от руки линию: сервер кладёт её на дороги города и
 * сохраняет маршрут. Загрузки geojson для маршрута больше нет — линию рисуют.
 *
 * Идёт через apiFetch, а не через uploadGeometry: тело обычный JSON, значит
 * пароль подставится сам и 401 обработается как везде. Ручная возня с
 * adminHeaders() нужна только тем трём функциям, что строят multipart или
 * разбирают пустой 204.
 */
export function drawRouteGeometry(
  citySlug: string,
  routeSlug: string,
  stroke: [number, number][],
): Promise<Route> {
  return apiFetch(`/cities/${citySlug}/routes/${routeSlug}/geometry`, {
    method: 'POST',
    body: JSON.stringify({ stroke }),
  })
}

export function getRoadsGeometry(citySlug: string): Promise<unknown> {
  return apiFetch(`/cities/${citySlug}/roads-geometry`)
}

export function getRouteGeometry(
  citySlug: string,
  routeSlug: string,
): Promise<unknown> {
  return apiFetch(`/cities/${citySlug}/routes/${routeSlug}/geometry`)
}

async function uploadGeometry<T>(path: string, file: File): Promise<T> {
  // Content-Type не ставим руками — браузер сам допишет boundary.
  const form = new FormData()
  form.append('file', file)
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'PUT',
    body: form,
    headers: adminHeaders(),
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401) forgetAdminSession()
    throw new Error(body?.detail ?? `HTTP ${response.status}`)
  }
  return (body as ApiEnvelope<T>).data
}

/** DELETE отдаёт 204 без тела — apiFetch ждёт конверт, поэтому отдельная обёртка. */
async function apiDelete(path: string): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'DELETE',
    headers: adminHeaders(),
  })
  if (!response.ok) {
    if (response.status === 401) forgetAdminSession()
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail ?? `HTTP ${response.status}`)
  }
}

/**
 * Задания маршрута. `includeInactive` — только админ-панель: скрытое задание
 * не должно попасться ни в списке маршрута, ни в выпадашке загрузки, иначе в
 * него зальют видео. Вернуть его можно с той же страницы, где оно видно.
 */
export function getRouteAssignments(
  citySlug: string,
  routeSlug: string,
  includeInactive = false,
): Promise<AssignmentsPage> {
  const hidden = includeInactive ? '&include_inactive=true' : ''
  return apiFetch(
    `/cities/${citySlug}/routes/${routeSlug}/assignments?page=1&page_size=50${hidden}`,
  )
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

/**
 * Сводка маршрута, необязательно за период. Границы приходят календарными
 * датами, а на сервер уходят моментами: часовой пояс знает браузер, и только он
 * может сказать, где начинается «третье мая». Конец превращается в границу
 * следующих суток — выбранный день входит в период целиком.
 */
export function getRouteSummary(
  citySlug: string,
  routeSlug: string,
  period: RoutePeriod = {},
): Promise<RouteSummary> {
  const query = new URLSearchParams()
  const from = period.from ? isoFromDateInput(period.from) : null
  const to = period.to ? isoFromDateInputExclusiveEnd(period.to) : null
  if (from) query.set('shot_from', from)
  if (to) query.set('shot_to', to)
  const suffix = query.toString()
  return apiFetch(
    `/cities/${citySlug}/routes/${routeSlug}/summary${suffix ? `?${suffix}` : ''}`,
  )
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

export function deleteGeozone(geozoneId: string): Promise<void> {
  return apiDelete(`/geozones/${geozoneId}`)
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

  // Заголовок админа обязателен: ручка под `require_admin`. Эта загрузка идёт
  // мимо `apiFetch` из-за multipart, поэтому его легко забыть — и тогда экран
  // под паролем получает 401 на ровном месте.
  const response = await fetch(`${API_BASE}/cities/${citySlug}/catalog/imports`, {
    method: 'POST',
    body: form,
    headers: adminHeaders(),
  })
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    if (response.status === 401) forgetAdminSession()
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

/** Снять каталог города с показа. Вернуть — обычным `restoreCatalogImport`. */
export function hideCatalogImport(importId: string): Promise<CatalogImport> {
  return apiFetch(`/catalog/imports/${importId}/hide`, { method: 'POST' })
}

export function deleteCatalogImport(importId: string): Promise<void> {
  return apiDelete(`/catalog/imports/${importId}`)
}
