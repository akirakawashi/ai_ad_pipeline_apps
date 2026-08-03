import { useEffect, useRef, useState, type CSSProperties } from 'react'
import {
  createGeozone,
  deleteGeozone,
  getRouteGeozones,
  updateGeozone,
} from '../api'
import type { CreateGeozonePayload, Geozone } from '../types'
import { pluralZones } from '../utils/formatters'

interface RouteGeozonesProps {
  citySlug: string
  routeSlug: string
  routeName: string
  /**
   * Presigned-ссылка на исходное видео съёмки. Без неё панель работает так же,
   * только границы вводятся процентами руками — маршрут можно разметить до
   * того, как по нему хоть раз проехали.
   */
  sourceUrl?: string
}

/** Черновик участка. Проценты держим строками: поле ввода бывает пустым. */
interface Draft {
  name: string
  description: string
  startPercent: string
  endPercent: string
  coefficient: string
}

const EMPTY_DRAFT: Draft = {
  name: '',
  description: '',
  startPercent: '',
  endPercent: '',
  coefficient: '1.5',
}

const clamp01 = (value: number): number => Math.min(1, Math.max(0, value))

const byStart = (first: Geozone, second: Geozone): number =>
  first.start_fraction - second.start_fraction

function formatClock(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  const total = Math.round(seconds)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

/** Доля → проценты для показа и для полей ввода: не длиннее одного знака. */
const percentText = (fraction: number): string =>
  String(Math.round(fraction * 1000) / 10)

/**
 * Проценты → доля с шагом 0.01 %. Без округления 35 % превращается в
 * 0.35000000000000003, и это число потом видно в API и в базе.
 */
const toFraction = (percent: number): number => Math.round(percent * 100) / 10_000

function parsePercent(value: string): number | null {
  const text = value.trim().replace(',', '.')
  if (text === '') return null
  const parsed = Number(text)
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) return null
  return parsed
}

function errorMessage(reason: unknown): string {
  return reason instanceof Error ? reason.message : String(reason)
}

function bandColor(coefficient: number): string {
  if (coefficient > 1) return 'var(--accent)'
  if (coefficient < 1) return 'var(--warning)'
  return 'var(--muted)'
}

function draftFrom(zone: Geozone): Draft {
  return {
    name: zone.name,
    description: zone.description,
    startPercent: percentText(zone.start_fraction),
    endPercent: percentText(zone.end_fraction),
    coefficient: String(zone.coefficient),
  }
}

/**
 * Черновик → тело запроса. Строка в ответе — готовое сообщение об ошибке:
 * бэкенд те же правила проверяет заново, здесь они только ради быстрой реакции.
 */
function toPayload(draft: Draft): CreateGeozonePayload | string {
  const name = draft.name.trim()
  if (name === '') return 'Название участка обязательно.'

  const start = parsePercent(draft.startPercent)
  const end = parsePercent(draft.endPercent)
  if (start === null || end === null) {
    return 'Границы задаются процентами от 0 до 100.'
  }
  if (start >= end) return 'Начало участка должно быть строго раньше конца.'

  const coefficient = Number(draft.coefficient.trim().replace(',', '.'))
  if (!(coefficient > 0)) return 'Коэффициент должен быть больше нуля.'

  return {
    name,
    description: draft.description.trim(),
    start_fraction: toFraction(start),
    end_fraction: toFraction(end),
    coefficient,
  }
}

function draftRange(draft: Draft): { left: number; width: number } | null {
  const start = parsePercent(draft.startPercent)
  const end = parsePercent(draft.endPercent)
  if (start === null || end === null || start >= end) return null
  return { left: start / 100, width: (end - start) / 100 }
}

/**
 * Зоны значимости маршрута: список, создание и правка.
 *
 * Границы — доли времени проезда, поэтому единица ввода процент: 0 % — старт
 * маршрута, 100 % — финиш. Разметка принадлежит маршруту, а не съёмке: сделали
 * один раз, применяется ко всем проездам, включая будущие.
 *
 * Способа ввода два, и они пишут в один черновик: кнопки «Начало здесь» /
 * «Конец здесь» по играющему видео (быстро, останавливать проезд не нужно) и те
 * же границы процентами руками — этим маршрут размечается до первой съёмки.
 */
export function RouteGeozones({
  citySlug,
  routeSlug,
  routeName,
  sourceUrl,
}: RouteGeozonesProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [expanded, setExpanded] = useState(false)
  const [zones, setZones] = useState<Geozone[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)

  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editDraft, setEditDraft] = useState<Draft>(EMPTY_DRAFT)
  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

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

  // Где сейчас голова воспроизведения, долей. null — видео нет или не готово,
  // и тогда кнопок отметки не будет вовсе.
  const currentFraction =
    sourceUrl && duration > 0 ? clamp01(currentTime / duration) : null

  const seekTo = (fraction: number) => {
    const video = videoRef.current
    if (video && duration > 0) video.currentTime = clamp01(fraction) * duration
  }

  const addZone = async () => {
    const payload = toPayload(draft)
    if (typeof payload === 'string') {
      setFormError(payload)
      return
    }
    setSaving(true)
    setFormError(null)
    try {
      const created = await createGeozone(citySlug, routeSlug, payload)
      setZones((prev) => [...prev, created].sort(byStart))
      setDraft(EMPTY_DRAFT)
    } catch (reason) {
      setFormError(errorMessage(reason))
    } finally {
      setSaving(false)
    }
  }

  const startEdit = (zone: Geozone) => {
    setEditingId(zone.id)
    setEditDraft(draftFrom(zone))
    setFormError(null)
  }

  const saveEdit = async () => {
    if (editingId === null) return
    const payload = toPayload(editDraft)
    if (typeof payload === 'string') {
      setFormError(payload)
      return
    }
    setSaving(true)
    setFormError(null)
    try {
      // Отправляем все поля: это правка участка целиком, а не точечный PATCH.
      const updated = await updateGeozone(editingId, payload)
      setZones((prev) =>
        prev.map((zone) => (zone.id === updated.id ? updated : zone)).sort(byStart),
      )
      setEditingId(null)
    } catch (reason) {
      setFormError(errorMessage(reason))
    } finally {
      setSaving(false)
    }
  }

  const removeZone = async (id: string) => {
    setSaving(true)
    try {
      await deleteGeozone(id)
      setZones((prev) => prev.filter((zone) => zone.id !== id))
      if (editingId === id) setEditingId(null)
      setError(null)
    } catch (reason) {
      setError(errorMessage(reason))
    } finally {
      setSaving(false)
    }
  }

  // Активный черновик один: либо создаём участок, либо правим открытый. Кнопки
  // отметки пишут именно в него, поэтому годятся и для правки границ.
  const activeDraft = editingId === null ? draft : editDraft
  const setActiveDraft = (patch: Partial<Draft>) =>
    editingId === null
      ? setDraft((current) => ({ ...current, ...patch }))
      : setEditDraft((current) => ({ ...current, ...patch }))

  const markEdge = (edge: 'start' | 'end') => {
    if (currentFraction === null) return
    const percent = percentText(currentFraction)
    setActiveDraft(edge === 'start' ? { startPercent: percent } : { endPercent: percent })
  }

  /** Отмеченная граница в минутах текущего видео — подпись на кнопке. */
  const edgeClock = (value: string): string | null => {
    const percent = parsePercent(value)
    if (percent === null || duration <= 0) return null
    return formatClock((percent / 100) * duration)
  }

  const startClock = edgeClock(activeDraft.startPercent)
  const endClock = edgeClock(activeDraft.endPercent)

  const preview = draftRange(activeDraft)

  return (
    <section className="panel geozone-panel">
      <header className="geozone-head">
        <div>
          <h2>Зоны значимости</h2>
          <p>
            {routeName} · {pluralZones(zones.length)}. Значимость места — множитель
            к заметности; неразмеченные промежутки считаются с 1.
          </p>
        </div>
        <button className="secondary" onClick={() => setExpanded((value) => !value)}>
          {expanded ? 'Свернуть' : zones.length > 0 ? 'Открыть' : 'Разметить'}
        </button>
      </header>

      {error && <p className="geozone-error">{error}</p>}
      {loading && <p className="geozone-hint">Загрузка участков…</p>}

      {expanded && (
        <div className="geozone-body">
          <p className="geozone-hint">
            {sourceUrl
              ? 'Границы — доли проезда: 0 % — старт маршрута, 100 % — финиш. Смотрите видео и отмечайте кнопками ниже — проценты подставятся сами, набирать их руками не обязательно. Разметка принадлежит маршруту и применится ко всем его видео.'
              : 'Границы — доли проезда: 0 % — старт маршрута, 100 % — финиш. Разметка принадлежит маршруту и применяется ко всем его видео, включая будущие, — видео для этого не нужно.'}
          </p>

          {sourceUrl && (
            <video
              ref={videoRef}
              className="geozone-video"
              src={sourceUrl}
              controls
              preload="metadata"
              onLoadedMetadata={(event) =>
                setDuration(event.currentTarget.duration || 0)
              }
              onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
            />
          )}

          <GeozoneRuler
            zones={zones}
            preview={preview}
            playhead={currentFraction}
            onSeek={sourceUrl ? seekTo : undefined}
          />

          {/* Главный способ разметки, когда есть видео: кнопки берут текущий
              момент, останавливать проезд не нужно. Пишут в тот же черновик,
              что и поля процентов, — в том числе в открытую правку участка. */}
          {sourceUrl && (
            <div className="geozone-controls">
              <button
                className="secondary"
                disabled={duration <= 0 || saving}
                onClick={() => markEdge('start')}
              >
                Начало здесь{startClock ? ` · ${startClock}` : ''}
              </button>
              <button
                className="secondary"
                disabled={duration <= 0 || saving}
                onClick={() => markEdge('end')}
              >
                Конец здесь{endClock ? ` · ${endClock}` : ''}
              </button>
              <span className="geozone-hint">
                {editingId === null
                  ? 'Видео можно не останавливать — момент берётся на ходу.'
                  : 'Отметки уходят в участок, который правите.'}
              </span>
            </div>
          )}

          {editingId === null && (
            <div className="geozone-form">
              <ZoneFields draft={draft} onChange={setDraft} disabled={saving} />
              <div className="geozone-form-actions">
                <button className="primary" disabled={saving} onClick={addZone}>
                  {saving ? 'Сохранение…' : 'Добавить участок'}
                </button>
                {(draft.name !== '' || draft.startPercent !== '') && (
                  <button
                    className="ghost-button"
                    disabled={saving}
                    onClick={() => {
                      setDraft(EMPTY_DRAFT)
                      setFormError(null)
                    }}
                  >
                    Очистить
                  </button>
                )}
              </div>
            </div>
          )}

          {formError && <p className="geozone-error">{formError}</p>}

          {zones.length === 0 ? (
            <p className="geozone-hint">
              Участков нет — весь маршрут считается с коэффициентом 1.
            </p>
          ) : (
            <ul className="geozone-list">
              {zones.map((zone) =>
                zone.id === editingId ? (
                  <li key={zone.id} className="geozone-row is-editing">
                    <ZoneFields
                      draft={editDraft}
                      onChange={setEditDraft}
                      disabled={saving}
                    />
                    <div className="geozone-form-actions">
                      <button className="primary" disabled={saving} onClick={saveEdit}>
                        {saving ? 'Сохранение…' : 'Сохранить'}
                      </button>
                      <button
                        className="ghost-button"
                        disabled={saving}
                        onClick={() => setEditingId(null)}
                      >
                        Отмена
                      </button>
                    </div>
                  </li>
                ) : (
                  <li key={zone.id} className="geozone-row">
                    <span
                      className="geozone-swatch"
                      style={{ background: bandColor(zone.coefficient) } as CSSProperties}
                    />
                    <div className="geozone-row-copy">
                      <span className="geozone-row-name">
                        {zone.name} <em>×{zone.coefficient}</em>
                      </span>
                      <span className="geozone-row-range">
                        {percentText(zone.start_fraction)}–
                        {percentText(zone.end_fraction)} %
                        {duration > 0 && (
                          <em>
                            {' '}
                            · {formatClock(zone.start_fraction * duration)}–
                            {formatClock(zone.end_fraction * duration)}
                          </em>
                        )}
                      </span>
                      {zone.description !== '' && (
                        <p className="geozone-row-description">{zone.description}</p>
                      )}
                    </div>
                    <span className="row-actions">
                      <button
                        className="ghost-button"
                        disabled={saving}
                        onClick={() => startEdit(zone)}
                      >
                        Править
                      </button>
                      <button
                        className="geozone-delete"
                        disabled={saving}
                        onClick={() => void removeZone(zone.id)}
                      >
                        Удалить
                      </button>
                    </span>
                  </li>
                ),
              )}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

/**
 * Поля участка. Проценты тут — способ набрать границы руками или поправить то,
 * что отметили кнопками по видео: и то и другое пишет в один черновик.
 */
function ZoneFields({
  draft,
  onChange,
  disabled,
}: {
  draft: Draft
  onChange: (draft: Draft) => void
  disabled: boolean
}) {
  const set = (patch: Partial<Draft>) => onChange({ ...draft, ...patch })

  return (
    <div className="geozone-fields">
      <label className="field geozone-field-wide">
        Название
        <input
          className="text-input"
          placeholder="Например, «Центр»"
          value={draft.name}
          disabled={disabled}
          onChange={(event) => set({ name: event.target.value })}
        />
      </label>

      <label className="field">
        Начало, %
        <input
          className="text-input"
          type="number"
          min="0"
          max="100"
          step="0.1"
          value={draft.startPercent}
          disabled={disabled}
          onChange={(event) => set({ startPercent: event.target.value })}
        />
      </label>

      <label className="field">
        Конец, %
        <input
          className="text-input"
          type="number"
          min="0"
          max="100"
          step="0.1"
          value={draft.endPercent}
          disabled={disabled}
          onChange={(event) => set({ endPercent: event.target.value })}
        />
      </label>

      <label className="field">
        Коэффициент
        <input
          className="text-input"
          type="number"
          min="0.1"
          step="0.1"
          value={draft.coefficient}
          disabled={disabled}
          onChange={(event) => set({ coefficient: event.target.value })}
        />
      </label>

      <label className="field geozone-field-wide">
        Описание — зачем участку такой коэффициент
        <textarea
          className="text-input geozone-textarea"
          rows={2}
          placeholder="Пешеходный поток, светофор на перекрёстке — стоим до 40 секунд"
          value={draft.description}
          disabled={disabled}
          onChange={(event) => set({ description: event.target.value })}
        />
      </label>
    </div>
  )
}

/**
 * Линейка 0…100 % с полосами участков. Работает и без видео: показывает, что
 * размечено и где остались дыры. С видео добавляется бегунок и перемотка кликом.
 */
function GeozoneRuler({
  zones,
  preview,
  playhead,
  onSeek,
}: {
  zones: Geozone[]
  preview: { left: number; width: number } | null
  playhead: number | null
  onSeek?: (fraction: number) => void
}) {
  return (
    <div className="geozone-ruler">
      <div
        className={`geozone-timeline${onSeek ? ' is-seekable' : ''}`}
        onClick={
          onSeek &&
          ((event) => {
            const rect = event.currentTarget.getBoundingClientRect()
            if (rect.width > 0) onSeek((event.clientX - rect.left) / rect.width)
          })
        }
      >
        {zones.map((zone) => (
          <div
            key={zone.id}
            className="geozone-band"
            style={
              {
                left: `${zone.start_fraction * 100}%`,
                width: `${(zone.end_fraction - zone.start_fraction) * 100}%`,
                '--band': bandColor(zone.coefficient),
              } as CSSProperties
            }
            title={`${zone.name} · ×${zone.coefficient}`}
          >
            <span>
              {zone.name} ×{zone.coefficient}
            </span>
          </div>
        ))}
        {preview && (
          <div
            className="geozone-selection"
            style={{
              left: `${preview.left * 100}%`,
              width: `${preview.width * 100}%`,
            }}
          />
        )}
        {playhead !== null && (
          <div className="geozone-playhead" style={{ left: `${playhead * 100}%` }} />
        )}
      </div>
      <div className="geozone-scale" aria-hidden="true">
        <span>0 %</span>
        <span>25 %</span>
        <span>50 %</span>
        <span>75 %</span>
        <span>100 %</span>
      </div>
    </div>
  )
}
