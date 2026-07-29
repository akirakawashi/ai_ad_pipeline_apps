export interface Artifact {
  id: string
  artifact_type: string
  object_key: string
  content_type: string
  size_bytes: number
  created_at: string
}

export interface RunEvent {
  id: string
  stage: string
  progress: number
  message: string | null
  created_at: string
}

/** Человек из справочника: постановщик задания или оператор съёмки. */
export interface User {
  id: string
  full_name: string
  is_active: boolean
  created_at: string | null
}

export interface CityRef {
  id: string
  slug: string
  name: string
}

export interface RouteRef {
  id: string
  slug: string
  name: string
  color_hex: string | null
}

/** Ссылка на задание с карточки видео. */
export interface RunAssignmentRef {
  assignment_id: string
  sequence_number: number
  title: string
  route: RouteRef
  city: CityRef
}

export interface Route {
  id: string
  slug: string
  name: string
  color_label: string | null
  color_hex: string | null
  description: string | null
  /** Есть ли залитая линия. Сама геометрия — отдельным запросом: она тяжёлая. */
  has_geometry: boolean
  display_order: number
  /** false — маршрут скрыт: пропал из выбора, его задания и съёмки на месте. */
  is_active: boolean
  assignment_count: number
  video_count: number
}

export interface City {
  id: string
  slug: string
  name: string
  region: string | null
  /** Есть ли залитый дорожный слой. Сам слой — до полутора мегабайт, отдельно. */
  has_roads_geometry: boolean
  display_order: number
  /** false — город скрыт: виден только в справочниках, чтобы было чем вернуть. */
  is_active: boolean
  route_count: number
  assignment_count: number
  video_count: number
}

export interface CityDetail extends City {
  routes: Route[]
}

/** Тело POST города. Слаг задаётся один раз: он в URL. */
export interface CityPayload {
  slug: string
  name: string
  region?: string | null
  display_order?: number
}

/** Тело PATCH города: отсутствующий ключ = «не менять». Слага здесь нет. */
export interface CityUpdatePayload {
  name?: string
  region?: string | null
  display_order?: number
  /** Скрыть/показать. Удаления города нет — снос утащил бы задания и съёмки. */
  is_active?: boolean
}

export interface RoutePayload {
  slug: string
  name: string
  color_label?: string | null
  color_hex?: string | null
  description?: string | null
  display_order?: number
}

export interface RouteUpdatePayload {
  name?: string
  color_label?: string | null
  color_hex?: string | null
  description?: string | null
  display_order?: number
  /** Скрыть/показать. Удаления маршрута нет. */
  is_active?: boolean
}

export interface AssignmentStatusCounts {
  uploading: number
  upload_failed: number
  queued: number
  processing: number
  completed: number
  processing_failed: number
}

export interface Assignment {
  id: string
  sequence_number: number
  /** Отображаемое имя: своё название либо «Задание №N · дата». */
  title: string
  /** Хранимое название, null — своего нет. Форма правит именно его. */
  custom_title: string | null
  description: string | null
  route: RouteRef
  city: CityRef
  /** Постановщик задания. */
  author: User | null
  /** Плановое окно — его задаёт постановщик. */
  planned_start_at: string | null
  planned_end_at: string | null
  /** Фактическое окно из времён съёмок. Не хранится, считается сервером. */
  actual_start_at: string | null
  actual_end_at: string | null
  video_count: number
  status_counts: AssignmentStatusCounts
  /** Скрытое задание видно только в админке — там же его и возвращают. */
  is_active: boolean
  created_at: string
}

/** Тело POST/PATCH задания. Отсутствующий ключ в PATCH = «не менять». */
export interface AssignmentPayload {
  title?: string | null
  description?: string | null
  planned_start_at?: string | null
  planned_end_at?: string | null
  author_user_id?: string | null
  /** Только PATCH: «скрыть» и «показать». Удаления задания нет. */
  is_active?: boolean
}

export interface AssignmentsPage {
  items: Assignment[]
  page: number
  page_size: number
  total: number
}

/** Что считаем «типичной» съёмкой. Выбор живёт только на фронте. */
export type Aggregate = 'mean' | 'median'

/**
 * Величина «на съёмку»: две оценки центра и разброс между съёмками. Сервер
 * отдаёт обе сразу — переключение это показ, а не пересчёт. Разброс общий:
 * он про то, как разошлись проезды, а не про выбранную оценку.
 */
export interface MetricStat {
  mean: number
  median: number
  std: number
}

export interface ShootingBrand {
  brand: string
  objects_count: number
  visibility_index: number
}

/**
 * Сырые метрики одной съёмки — единица учёта во всей аналитике. И задание, и
 * маршрут считаются из списка таких записей напрямую, без промежуточных средних.
 */
export interface ShootingMetrics {
  run_id: string
  source_name: string
  /** Когда снимали, а не когда обрабатывали. */
  shot_started_at: string | null
  duration_sec: number
  objects_count: number
  visibility_index: number
  brands: ShootingBrand[]
}

/** То же плюс задание: на уровне маршрута его показываем в списке. */
export interface RouteShootingMetrics extends ShootingMetrics {
  assignment: RunAssignmentRef
}

/** Доли здесь нет: она зависит от выбранной оценки и считается на месте показа. */
export interface RollupBrand {
  brand: string
  objects_per_shooting: MetricStat
  visibility_per_shooting: MetricStat
}

export interface RollupTotals {
  shootings_total: number
  shootings_completed: number
  /** Сумма — «сколько наснимали». Остальное усредняется по съёмкам. */
  duration_sec: number
  objects_per_shooting: MetricStat
  visibility_per_shooting: MetricStat
}

export interface AssignmentSummary {
  assignment: Assignment
  totals: RollupTotals
  brands: RollupBrand[]
  shootings: ShootingMetrics[]
}

/** Свёртка маршрута: та же форма, тот же код, но список съёмок длиннее. */
export interface RouteSummary {
  route: Route
  assignments_total: number
  totals: RollupTotals
  brands: RollupBrand[]
  shootings: RouteShootingMetrics[]
}


export interface PipelineRun {
  run_id: string
  source_name: string
  source_content_type: string | null
  source_size_bytes: number
  status: string
  stage: string
  progress: number
  status_message: string | null
  error_code: string | null
  error_message: string | null
  fps: number | null
  frame_count: number | null
  frame_stride: number | null
  duration_sec: number | null
  width: number | null
  height: number | null
  created_at: string
  upload_completed_at: string | null
  started_at: string | null
  completed_at: string | null
  updated_at: string
  /** Когда снимали. Не путать со started_at выше — там начало обработки. */
  shot_started_at: string | null
  /** Считает сервер: shot_started_at + duration_sec. Не хранится. */
  shot_finished_at: string | null
  /**
   * null означает «связь не запрашивали», а не «задания нет»: съёмок вне
   * маршрута не бывает. Так отвечает `/assignments/{id}/runs` — там задание и
   * так известно из адреса, и грузить его к каждой съёмке незачем.
   */
  assignment: RunAssignmentRef | null
  operator: User | null
  artifacts: Artifact[]
  events: RunEvent[]
}

/** Тело PATCH съёмки. Ход обработки этим не меняется. */
export interface ShootingPayload {
  shot_started_at?: string | null
  operator_user_id?: string | null
}

export interface RunsPage {
  items: PipelineRun[]
  page: number
  page_size: number
  total: number
}

export interface UploadTarget {
  method: string
  url: string
  headers: Record<string, string>
}

export interface CreateRunResult {
  run_id: string
  status: string
  upload: UploadTarget
}

export interface BrandSummary {
  brand: string
  object_count?: number
  sum_visibility_value?: number
  visibility_share?: number
  mean_final_brand_conf?: number
}

export interface RunSummary {
  run: PipelineRun
  totals: {
    total_objects?: number
    visibility_index?: number
  }
  brands: BrandSummary[]
}

export interface RunObject {
  object_id?: number
  track_id: number
  business_brand: string
  first_timestamp_sec: number
  last_timestamp_sec: number
  visible_duration_sec: number
  detections_count: number
  final_brand_conf: number
  visibility_value: number
  best_timestamp_sec: number
  crop_url?: string | null
}

export interface RunObjects {
  run_id: string
  objects: RunObject[]
}

export interface TimelinePoint {
  bucket_start_sec: number
  business_brand: string
  detection_count: number
  intensity_sum: number
}

export interface RunTimeline {
  run_id: string
  bucket_seconds: number
  points: TimelinePoint[]
}

export interface Playback {
  source_url: string | null
}

/** Участок значимости маршрута: доля [start, end) времени видео и множитель β. */
export interface Geozone {
  id: string
  route_id: string
  name: string
  /** Зачем такой коэффициент. Может быть пустым, но не null. */
  description: string
  start_fraction: number
  end_fraction: number
  coefficient: number
  created_at: string | null
  updated_at: string | null
}

/** Тело POST участка: границы — доли [0,1] от длительности видео. */
export interface CreateGeozonePayload {
  name: string
  description: string
  start_fraction: number
  end_fraction: number
  coefficient: number
}

/** Тело PATCH участка: отсутствующий ключ = «не менять», пустая строка стирает. */
export interface UpdateGeozonePayload {
  name?: string
  description?: string
  start_fraction?: number
  end_fraction?: number
  coefficient?: number
}

export interface OverlayObject {
  object_id: number | null
  track_id: number | null
  brand: string
  label: string
  color: string
  bbox: [number, number, number, number]
  det_conf: number
  brand_conf: number
  area_ratio: number
  intensity: number
  visibility_value: number
  card_priority?: number
}

export interface OverlayFrame {
  frame_index: number
  timestamp_sec: number
  objects: OverlayObject[]
}

export interface OverlayPayload {
  video: {
    width: number
    height: number
    fps: number
    frame_count: number
    frame_stride: number
  }
  display?: {
    max_cards_per_frame?: number
    fields?: string[]
  }
  frames: OverlayFrame[]
}

export interface AdStructure {
  id: string
  city_id: string
  address: string
  latitude: number
  longitude: number
  /** Сколько щитов в одной точке: стоят треугольником, друг над другом. */
  surfaces_count: number
}

export interface PaginatedAdStructures {
  items: AdStructure[]
  page: number
  page_size: number
  total: number
}

export interface CatalogImport {
  id: string
  city_id: string
  /** Пусто, пока пак не применён: отменённые не тратят номера. */
  revision: number | null
  status: 'parsed' | 'applied' | 'cancelled'
  is_current: boolean
  file_names: string[]
  rows_read: number
  rows_rejected: number
  points_total: number
  files_rejected: number
  uploaded_by: User | null
  applied_at: string | null
  created_at: string | null
}

export interface RejectedFile {
  file_name: string
  reason: string
}

export interface CatalogRowError {
  file_name: string
  row_number: number
  reason: string
}

/** Что произойдёт, если применить пак. Показывается до подтверждения. */
export interface CatalogImportReport {
  catalog_import: CatalogImport
  points_before: number
  points_after: number
  added: number
  removed: number
  collapsed_rows: number
  rejected_files: RejectedFile[]
  row_errors: CatalogRowError[]
  files_with_extra_sheets: string[]
}
