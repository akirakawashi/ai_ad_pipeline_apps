import { useEffect, useRef, useState, type CSSProperties } from 'react'
import {
  createGeozone,
  deleteGeozone,
  getRouteGeozones,
  updateGeozone,
} from '../api'
import type { Geozone, UpdateGeozonePayload } from '../types'

interface GeozoneMarkerProps {
  citySlug: string
  routeSlug: string
  routeName: string
  /** Presigned-ссылка на исходное видео съёмки — холст для разметки. */
  sourceUrl: string
}

const clamp01 = (value: number): number => Math.min(1, Math.max(0, value))

function formatClock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const total = Math.round(seconds)
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

function bandColor(coefficient: number): string {
  if (coefficient > 1) return 'var(--accent)'
  if (coefficient < 1) return 'var(--warning)'
  return 'var(--muted)'
}

const byStart = (first: Geozone, second: Geozone): number =>
  first.start_fraction - second.start_fraction

/**
 * Разметка геозон на исходном видео съёмки. Границы — свойство маршрута:
 * отметил один раз, применится ко всем его съёмкам. Кликаешь «начало»/«конец»,
 * задаёшь коэффициент — участок на таймлайне. β считает бэкенд из этих границ.
 */
export function GeozoneMarker({
  citySlug,
  routeSlug,
  routeName,
  sourceUrl,
}: GeozoneMarkerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [expanded, setExpanded] = useState(false)
  const [zones, setZones] = useState<Geozone[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [startSec, setStartSec] = useState<number | null>(null)
  const [endSec, setEndSec] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [coefficient, setCoefficient] = useState('1.5')
  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  // Черновики коэффициентов существующих участков: id → строка ввода.
  const [coefDraft, setCoefDraft] = useState<Record<string, string>>({})

  useEffect(() => {
    // loading стартует true — синхронный setState в теле эффекта не нужен и
    // ругается линтер. Маршрут у компонента один, повторной загрузки нет.
    let active = true
    getRouteGeozones(citySlug, routeSlug)
      .then((loaded) => {
        if (active) {
          setZones([...loaded].sort(byStart))
          setError(null)
        }
      })
      .catch((reason) => active && setError(errorMessage(reason)))
      .finally(() => active && setLoading(false))
    return () => {
      active = false
    }
  }, [citySlug, routeSlug])

  const startFraction = startSec !== null && duration > 0 ? startSec / duration : null
  const endFraction = endSec !== null && duration > 0 ? endSec / duration : null
  const canAdd =
    duration > 0 &&
    startSec !== null &&
    endSec !== null &&
    startSec < endSec &&
    name.trim() !== '' &&
    Number(coefficient) > 0

  const seekTo = (fraction: number) => {
    const video = videoRef.current
    if (video && duration > 0) video.currentTime = clamp01(fraction) * duration
  }

  const addZone = async () => {
    if (!canAdd || startSec === null || endSec === null) return
    setSaving(true)
    setFormError(null)
    try {
      const created = await createGeozone(citySlug, routeSlug, {
        name: name.trim(),
        start_fraction: clamp01(startSec / duration),
        end_fraction: clamp01(endSec / duration),
        coefficient: Number(coefficient),
      })
      setZones((prev) => [...prev, created].sort(byStart))
      setStartSec(null)
      setEndSec(null)
      setName('')
    } catch (reason) {
      setFormError(errorMessage(reason))
    } finally {
      setSaving(false)
    }
  }

  const patchZone = async (id: string, payload: UpdateGeozonePayload) => {
    try {
      const updated = await updateGeozone(id, payload)
      setZones((prev) => prev.map((zone) => (zone.id === id ? updated : zone)).sort(byStart))
      setError(null)
    } catch (reason) {
      setError(errorMessage(reason))
    }
  }

  const saveCoefficient = async (zone: Geozone) => {
    const draft = coefDraft[zone.id]
    if (draft === undefined) return
    const next = Number(draft)
    if (!(next > 0)) {
      setError('Коэффициент должен быть больше нуля.')
      return
    }
    if (next !== zone.coefficient) await patchZone(zone.id, { coefficient: next })
    setCoefDraft((drafts) => {
      const rest = { ...drafts }
      delete rest[zone.id]
      return rest
    })
  }

  const removeZone = async (id: string) => {
    try {
      await deleteGeozone(id)
      setZones((prev) => prev.filter((zone) => zone.id !== id))
      setError(null)
    } catch (reason) {
      setError(errorMessage(reason))
    }
  }

  return (
    <section className="panel geozone-panel">
      <header className="geozone-head">
        <div>
          <h2>Геозоны маршрута</h2>
          <p>
            {routeName} · {zones.length}{' '}
            {zones.length === 1 ? 'участок' : 'участков'}. Значимость места —
            множитель к заметности.
          </p>
        </div>
        <button
          className="secondary"
          onClick={() => setExpanded((value) => !value)}
        >
          {expanded ? 'Свернуть' : 'Разметить'}
        </button>
      </header>

      {error && <p className="geozone-error">{error}</p>}
      {loading && <p className="geozone-hint">Загрузка участков…</p>}

      {expanded && (
        <div className="geozone-body">
          <p className="geozone-hint">
            Размечаешь один раз на маршрут — применится ко всем его съёмкам.
            Смотри видео, отметь начало и конец участка, задай коэффициент.
          </p>

          <video
            ref={videoRef}
            className="geozone-video"
            src={sourceUrl}
            controls
            preload="metadata"
            onLoadedMetadata={(event) =>
              setDuration(event.currentTarget.duration || 0)
            }
            onTimeUpdate={(event) =>
              setCurrentTime(event.currentTarget.currentTime)
            }
          />

          <GeozoneTimeline
            zones={zones}
            duration={duration}
            currentTime={currentTime}
            startFraction={startFraction}
            endFraction={endFraction}
            onSeek={seekTo}
          />

          <div className="geozone-controls">
            <button
              className="secondary"
              disabled={duration <= 0}
              onClick={() => setStartSec(currentTime)}
            >
              Начало здесь{startSec !== null ? ` · ${formatClock(startSec)}` : ''}
            </button>
            <button
              className="secondary"
              disabled={duration <= 0}
              onClick={() => setEndSec(currentTime)}
            >
              Конец здесь{endSec !== null ? ` · ${formatClock(endSec)}` : ''}
            </button>
            <input
              className="geozone-name-input"
              placeholder="Название, например «Центр»"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
            <label className="geozone-coef-field">
              коэф
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={coefficient}
                onChange={(event) => setCoefficient(event.target.value)}
              />
            </label>
            <button className="primary" disabled={!canAdd || saving} onClick={addZone}>
              {saving ? 'Сохранение…' : 'Добавить участок'}
            </button>
          </div>
          {formError && <p className="geozone-error">{formError}</p>}

          {zones.length > 0 && (
            <ul className="geozone-list">
              {zones.map((zone) => (
                <li key={zone.id} className="geozone-row">
                  <span
                    className="geozone-swatch"
                    style={{ background: bandColor(zone.coefficient) } as CSSProperties}
                  />
                  <span className="geozone-row-name">{zone.name}</span>
                  <span className="geozone-row-range">
                    {formatClock(zone.start_fraction * duration)}–
                    {formatClock(zone.end_fraction * duration)}
                    <em>
                      {' '}
                      ({Math.round(zone.start_fraction * 100)}–
                      {Math.round(zone.end_fraction * 100)}%)
                    </em>
                  </span>
                  <label className="geozone-coef-field">
                    ×
                    <input
                      type="number"
                      step="0.1"
                      min="0.1"
                      value={coefDraft[zone.id] ?? String(zone.coefficient)}
                      onChange={(event) =>
                        setCoefDraft((drafts) => ({
                          ...drafts,
                          [zone.id]: event.target.value,
                        }))
                      }
                      onBlur={() => void saveCoefficient(zone)}
                    />
                  </label>
                  <button
                    className="geozone-delete"
                    title="Удалить участок"
                    onClick={() => void removeZone(zone.id)}
                  >
                    Удалить
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

function GeozoneTimeline({
  zones,
  duration,
  currentTime,
  startFraction,
  endFraction,
  onSeek,
}: {
  zones: Geozone[]
  duration: number
  currentTime: number
  startFraction: number | null
  endFraction: number | null
  onSeek: (fraction: number) => void
}) {
  const playhead = duration > 0 ? clamp01(currentTime / duration) : 0
  const selection =
    startFraction !== null && endFraction !== null && endFraction > startFraction
      ? { left: startFraction, width: endFraction - startFraction }
      : null

  return (
    <div
      className="geozone-timeline"
      onClick={(event) => {
        const rect = event.currentTarget.getBoundingClientRect()
        if (rect.width > 0) onSeek((event.clientX - rect.left) / rect.width)
      }}
    >
      {zones.map((zone) => {
        const left = `${zone.start_fraction * 100}%`
        const width = `${(zone.end_fraction - zone.start_fraction) * 100}%`
        return (
          <div
            key={zone.id}
            className="geozone-band"
            style={
              { left, width, '--band': bandColor(zone.coefficient) } as CSSProperties
            }
            title={`${zone.name} · ×${zone.coefficient}`}
          >
            <span>
              {zone.name} ×{zone.coefficient}
            </span>
          </div>
        )
      })}
      {selection && (
        <div
          className="geozone-selection"
          style={
            {
              left: `${selection.left * 100}%`,
              width: `${selection.width * 100}%`,
            } as CSSProperties
          }
        />
      )}
      <div className="geozone-playhead" style={{ left: `${playhead * 100}%` }} />
    </div>
  )
}
