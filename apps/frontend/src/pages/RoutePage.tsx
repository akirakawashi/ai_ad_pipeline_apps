import { useEffect, useState } from 'react'
import {
  createAssignment,
  getCity,
  getRouteAssignments,
  getRouteSummary,
} from '../api'
import { AssignmentForm } from '../components/AssignmentForm'
import { RouteSummaryPanel } from '../components/RouteSummaryPanel'
import { EmptyState, ErrorBanner } from '../components/common/Feedback'
import { PageHeader } from '../components/common/PageHeader'
import { RunsSkeleton } from '../components/common/Skeletons'
import { navigate } from '../routing'
import type { Assignment, AssignmentPayload, Route, RouteSummary } from '../types'
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
}: {
  citySlug: string
  routeSlug: string
}) {
  const [route, setRoute] = useState<Route | null>(null)
  const [cityName, setCityName] = useState('')
  const [assignments, setAssignments] = useState<Assignment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [summary, setSummary] = useState<RouteSummary | null>(null)
  const [creating, setCreating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

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
  // когда обработалась ещё одна съёмка — этот момент виден по счётчикам заданий.
  useEffect(() => {
    let disposed = false
    getRouteSummary(citySlug, routeSlug)
      .then((loaded) => {
        if (!disposed) setSummary(loaded)
      })
      .catch(() => undefined)
    return () => {
      disposed = true
    }
  }, [citySlug, routeSlug, completedVideos])

  const submit = (payload: AssignmentPayload) => {
    setSaving(true)
    setFormError(null)
    createAssignment(citySlug, routeSlug, payload)
      // Сразу внутрь задания: следующий шаг — загрузить в него съёмки.
      .then((assignment) => navigate(`/assignments/${assignment.id}`))
      .catch((reason) => {
        setFormError(String(reason))
        setSaving(false)
      })
  }

  const newAssignmentButton = (
    <button className="primary" onClick={() => setCreating(true)}>
      Новое задание
    </button>
  )

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
        actions={creating ? undefined : newAssignmentButton}
      />

      {error && <ErrorBanner text={error} />}

      {route?.description && <p className="route-description">{route.description}</p>}

      {creating && (
        <AssignmentForm
          submitLabel="Создать задание"
          busy={saving}
          error={formError}
          onSubmit={submit}
          onCancel={() => {
            setCreating(false)
            setFormError(null)
          }}
        />
      )}

      {loading && <RunsSkeleton />}

      {!loading && !error && !creating && !assignments.length && (
        <EmptyState
          text="На этом маршруте ещё нет заданий. Создайте первое."
          action={newAssignmentButton}
        />
      )}

      {summary && (
        <section className="route-summary">
          <header className="route-summary-head">
            <h2>Аналитика маршрута</h2>
            <p>
              Считается из съёмок напрямую, а не из средних по заданиям: иначе
              кампания из двух проездов весила бы столько же, сколько кампания из
              двадцати.
            </p>
          </header>
          <RouteSummaryPanel summary={summary} />
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
