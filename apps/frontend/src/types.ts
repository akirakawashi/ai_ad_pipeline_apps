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

/** Ссылка на замер с карточки видео. null — «Без маршрута». */
export interface RunMeasurementRef {
  measurement_id: string
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
  /** Путь относительно public/, без ведущего слэша: 'routes/simferopol/route_1.geojson'. */
  geojson_path: string
  display_order: number
  measurement_count: number
  video_count: number
}

export interface City {
  id: string
  slug: string
  name: string
  region: string | null
  /** Путь относительно public/, без ведущего слэша. */
  roads_geojson_path: string | null
  display_order: number
  route_count: number
  measurement_count: number
  video_count: number
}

export interface CityDetail extends City {
  routes: Route[]
}

export interface MeasurementStatusCounts {
  uploading: number
  upload_failed: number
  queued: number
  processing: number
  completed: number
  processing_failed: number
}

export interface RouteMeasurement {
  id: string
  sequence_number: number
  title: string
  route: RouteRef
  city: CityRef
  video_count: number
  status_counts: MeasurementStatusCounts
  created_at: string
}

export interface MeasurementsPage {
  items: RouteMeasurement[]
  page: number
  page_size: number
  total: number
}

export interface MeasurementTotals {
  total_objects: number
  visibility_index: number
  video_count: number
  completed_count: number
  duration_sec: number
}

export interface MeasurementSummary {
  measurement: RouteMeasurement
  totals: MeasurementTotals
  brands: BrandSummary[]
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
  /** null — «Без маршрута» либо связь не запрашивали. */
  measurement: RunMeasurementRef | null
  artifacts: Artifact[]
  events: RunEvent[]
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
  video_visibility_weighted_seconds?: number
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
  video_visibility_weighted_seconds: number
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
  visibility_score: number
}

export interface RunTimeline {
  run_id: string
  bucket_seconds: number
  points: TimelinePoint[]
}

export interface Playback {
  source_url: string | null
  annotated_url: string | null
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
  visibility_score: number
  overall_score: number
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
