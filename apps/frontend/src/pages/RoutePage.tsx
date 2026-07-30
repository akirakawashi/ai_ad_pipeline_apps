import { useEffect, useState } from 'react'
import { getCity, getRouteAssignments, getRouteSummary } from '../api'
import { RouteSummaryPanel } from '../components/RouteSummaryPanel'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { RunsSkeleton } from '../components/common/Skeletons'
import { navigate, routePath, type RoutePeriod } from '../routing'
import type { Assignment, Route, RouteSummary } from '../types'
import { formatPeriod, pluralAssignments } from '../utils/formatters'

function assignmentProgressLabel(assignment: Assignment): string {
  const { completed, processing, queued, uploading, processing_failed } =
    assignment.status_counts
  const parts: string[] = []
  if (completed) parts.push(`Готово ${completed}`)
  if (processing + queued + uploading) {
    parts.push(`В работе ${processing + queued + uploading}`)
  }
  if (processing_failed) parts.push(`Ошибок ${processing_failed}`)
  return parts.join(' · ') || 'Пусто'
}

export function RoutePage({
  citySlug,
  routeSlug,
  period,
}: {
  citySlug: string
  routeSlug: string
  period: RoutePeriod
}) {
  const [route, setRoute] = useState<Route | null>(null)
  const [cityName, setCityName] = useState('')
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<RouteSummary | null>(null)

  useEffect(() => {
    let disposed = false
    const load = () => {
      Promise.all([getCity(citySlug), getRouteAssignments(citySlug, routeSlug)])
        .then(([city, page]) => {
          if (disposed) return
          setCityName(city.name)
          setRoute(city.routes.find((item) => item.slug === routeSlug) ?? null)
          setAssignments(page.items)
        })
        .catch((reason) => {
          if (!disposed) setError(String(reason))
        })
        .finally(() => {
          if (!disposed) setLoading(false)
        })
    }
    load()
    // Задания показывают статус обработки — он меняется без нашего участия.
    const interval = window.setInterval(load, 5000)
    return () => {
      disposed = true
      window.clearInterval(interval)
    }
  }, [citySlug, routeSlug])

  const totalVideos = assignments.reduce(
    (sum, assignment) => sum + assignment.video_count,
    0,
  )
  const completedVideos = assignments.reduce(
    (sum, assignment) => sum + assignment.status_counts.completed,
    0,
  )

  // Сводка маршрута читает tracks.csv каждой готовой съёмки, поэтому её нельзя
  // тянуть на пятисекундном таймере вместе с заданиями. Перечитываем только
  // когда обработалась ещё одна съёмка (это видно по счётчикам заданий) или
  // когда поменяли период — там список съёмок другой, а считать его должен
  // сервер: вторая реализация усреднения разошлась бы с первой.
  // Границы разбираем на строки: объект периода приезжает из разбора адреса и
  // при каждом переходе новый, даже если даты те же. По самим датам эффект
  // срабатывает ровно тогда, когда окно действительно поменялось.
  const { from: periodFrom, to: periodTo } = period

  useEffect(() => {
    let disposed = false
    getRouteSummary(citySlug, routeSlug, { from: periodFrom, to: periodTo })
      .then((loaded) => {
        if (!disposed) setSummary(loaded)
      })
      .catch(() => undefined)
    return () => {
      disposed = true
    }
  }, [citySlug, routeSlug, completedVideos, periodFrom, periodTo])

  return (
    <div className="page">
      <PageHeader
        eyebrow={cityName || 'Маршрут'}
        title={route?.name ?? 'Задания маршрута'}
        description={
          route
            ? `${pluralAssignments(assignments.length)} · ${totalVideos} видео`
            : undefined
        }
      />

      {error && <ErrorBanner text={error} />}

      {route?.description && <p className="route-description">{route.description}</p>}

      {loading && <RunsSkeleton />}

      {/* Кнопки «Новое задание» здесь больше нет: задание заводят в админке.
          Пустой маршрут поэтому не предлагает создать, а говорит, где это
          делается, — иначе экран выглядел бы сломанным. */}
      {!loading && !error && !assignments.length && (
        <EmptyState text="На этом маршруте ещё нет заданий. Их заводят в админ-панели, на вкладке «Задания»." />
      )}

      {summary && (
        <section className="route-summary">
          <header className="route-summary-head">
            <h2>Аналитика маршрута</h2>
          </header>
          <RouteSummaryPanel
            summary={summary}
            period={period}
            onPeriodChange={(next) =>
              navigate(routePath(citySlug, routeSlug, next))
            }
          />
        </section>
      )}

      {assignments.length > 0 && (
        <header className="route-summary-head">
          <h2>Задания</h2>
          <p>Кампания на маршруте: серия съёмок с плановым окном.</p>
        </header>
      )}

      <div className="runs-grid">
        {assignments.map((assignment) => (
          <button
            className="run-card"
            key={assignment.id}
            onClick={() => navigate(`/assignments/${assignment.id}`)}
          >
            <div
              className="run-preview"
              style={
                assignment.route.color_hex
                  ? { borderColor: assignment.route.color_hex }
                  : undefined
              }
            >
              <span>▦</span>
            </div>
            <div className="run-copy">
              <div className="status status-queued">
                {assignment.video_count} видео
              </div>
              <h3>{assignment.title}</h3>
              <p>{assignmentProgressLabel(assignment)}</p>
              <p className="run-card-meta">
                {assignment.author?.full_name ?? 'Постановщик не указан'}
                {' · '}
                {formatPeriod(
                  assignment.planned_start_at,
                  assignment.planned_end_at,
                )}
              </p>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
