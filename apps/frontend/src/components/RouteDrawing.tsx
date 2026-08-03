import { useCallback, useEffect, useMemo, useState } from 'react'

import { drawRouteGeometry, getRoadsGeometry, getRouteGeometry } from '../api'
import type { Route } from '../types'
import { RouteMap, type GeoFeatureCollection } from './RouteMap'
import { ErrorBanner } from './common/Feedback'

type Stroke = [number, number][]

/**
 * Рисование линии маршрута поверх дорожного слоя города.
 *
 * Порядок намеренно такой: рисуешь целиком → «Подтвердить» → только тогда идут
 * расчёты. Иначе и нельзя: маршрут по дорогам подбирается для штриха целиком,
 * решение про каждый его кусок зависит от того, куда линия пойдёт дальше
 * (`domain/route_snapping.py`). Пока подтверждения нет, на карте видно ровно то,
 * что нарисовала рука, — сырую линию.
 *
 * **«Целиком» не значит «за один жест».** Линия набирается кусками: протяжка
 * даёт след, одиночный клик — точку, и то и другое дописывается к уже
 * нарисованному. Сорок километров одной непрерывной протяжкой — это сорок
 * километров без права отпустить кнопку, а на сложном узле рука нужна свободной:
 * приблизить, оглядеться, поставить три клика по поворотам. Отсюда и разделение
 * ролей у клавиш: Esc гасит режим рисования, **ничего не стирая**, Ctrl+Z
 * убирает последний кусок, Enter подтверждает.
 *
 * Попадать в дорогу точно не нужно: сервер кладёт линию на сеть сам, и промах
 * в пару десятков метров ничего не меняет. А вот между двумя кликами он проложит
 * **кратчайший** путь — поэтому клик ставится на каждом повороте, а не только в
 * начале и в конце. Это не вкусовщина, а замер: при кликах через 300 м длина
 * сходится с эталоном в пределах 4 % у шести маршрутов из семи, а при кликах
 * через 800 м расходится уже на четверть (`tests/test_route_snapping.py`).
 */
export function RouteDrawing({
  citySlug,
  route,
  onSaved,
}: {
  citySlug: string
  route: Route
  onSaved: (message: string) => void
}) {
  // Карта города хранится с меткой, чья она, и читается через производную
  // защиту — так во всём проекте (см. соглашение о данных, выбранных на
  // странице). Чистить состояние в эффекте нельзя: между сменой маршрута и
  // ответом сервера на экране оказалась бы карта прошлого города, по которой
  // можно было бы начать рисовать.
  const [loaded, setLoaded] = useState<{
    key: string
    roads: GeoFeatureCollection | null
    existing: GeoFeatureCollection | null
  } | null>(null)
  // Линия хранится кусками, а не одним списком точек, ровно ради шага назад:
  // куском отменяется то же, что было сделано одним действием — клик или след
  // протяжки. На сервер уходит склейка, там про куски никто не знает.
  const [segments, setSegments] = useState<Stroke[]>([])
  // История на один шаг: отменить последнее действие можно, отменить отменённое
  // — нет. Так решено намеренно (полноценная история тут не окупается), и
  // единственное, что для этого нужно, — помнить, был ли шаг назад уже сделан.
  const [undone, setUndone] = useState(false)
  // Рисование можно приостановить, не потеряв нарисованное: карта перестаёт
  // принимать клики, резинка гаснет, линия остаётся. Это то состояние, в котором
  // спокойно жмут «Подтвердить», не рискуя добавить лишнюю точку случайным
  // кликом мимо кнопки.
  const [paused, setPaused] = useState(false)
  // Проложенная линия, вернувшаяся с сервера. Пока она есть, экран показывает
  // результат, а не приглашает рисовать.
  const [result, setResult] = useState<GeoFeatureCollection | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const key = `${citySlug}/${route.slug}`
  const current = loaded?.key === key ? loaded : null
  const stroke = useMemo(() => segments.flat(), [segments])
  const canConfirm = stroke.length >= 2 && !saving
  const canUndo = segments.length > 0 && !undone && !result && !saving

  useEffect(() => {
    let cancelled = false
    void Promise.all([
      getRoadsGeometry(citySlug).catch(() => null),
      route.has_geometry ? getRouteGeometry(citySlug, route.slug).catch(() => null) : null,
    ]).then(([roadsGeometry, routeGeometry]) => {
      if (cancelled) return
      setLoaded({
        key: `${citySlug}/${route.slug}`,
        roads: (roadsGeometry as GeoFeatureCollection | null) ?? null,
        existing: (routeGeometry as GeoFeatureCollection | null) ?? null,
      })
    })
    return () => {
      cancelled = true
    }
  }, [citySlug, route.slug, route.has_geometry])

  const addSegment = useCallback((segment: Stroke) => {
    setSegments((previous) => [...previous, segment])
    // Новый кусок — новый шаг, который можно отменить. Иначе шаг назад работал
    // бы один раз за весь сеанс рисования.
    setUndone(false)
  }, [])

  const undo = useCallback(() => {
    setSegments((previous) => previous.slice(0, -1))
    setUndone(true)
  }, [])

  const confirm = useCallback(async () => {
    if (stroke.length < 2) return
    setSaving(true)
    setError('')
    try {
      await drawRouteGeometry(citySlug, route.slug, stroke)
      // Показываем, что получилось, вместо того чтобы закрыть экран: положить
      // линию на дороги — это решение алгоритма, и увидеть его человек должен
      // до того, как уйдёт со страницы. Штрих остаётся рядом для сравнения.
      const saved = (await getRouteGeometry(citySlug, route.slug)) as GeoFeatureCollection
      setResult(saved)
      // Сохранённое становится и «прежней линией»: нажмут «Перерисовать» —
      // под рукой должно лежать то, что в базе сейчас, а не то, что было при
      // открытии экрана.
      setLoaded((previous) =>
        previous && previous.key === key ? { ...previous, existing: saved } : previous,
      )
    } catch (cause) {
      // Штрих остаётся на карте: человек только что его вёл, и терять работу
      // из-за отказа сервера нельзя — «Перерисовать» он нажмёт сам, если решит.
      setError(cause instanceof Error ? cause.message : 'Не удалось проложить маршрут.')
    } finally {
      setSaving(false)
    }
  }, [citySlug, key, route.slug, stroke])

  const redraw = () => {
    setSegments([])
    setUndone(false)
    setPaused(false)
    setResult(null)
    setError('')
  }

  // Клавиши — только ускорители: всё, что они делают, есть на кнопках рядом, и
  // на кнопках же написано, какая клавиша что делает. Невидимых правил тут быть
  // не должно — экран открывают раз в несколько месяцев, заводя новый город.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null
      // Рядом на странице живут поля ввода админки: пока курсор в них, клавиши
      // принадлежат им, а не карте.
      if (target?.closest('input, textarea, select, [contenteditable="true"]')) return

      if (event.key === 'Escape') {
        // Esc не стирает — он опускает руку. Нарисованное остаётся на карте,
        // и его можно подтверждать, не боясь дописать лишний клик.
        if (paused || result) return
        event.preventDefault()
        setPaused(true)
        return
      }
      if (event.key === 'Enter' && !result) {
        if (!canConfirm) return
        event.preventDefault()
        void confirm()
        return
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        if (!canUndo) return
        event.preventDefault()
        undo()
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [canConfirm, canUndo, confirm, paused, result, undo])

  if (!current) {
    return <p className="muted">Загружаем карту города…</p>
  }

  if (!current.roads) {
    return (
      <p className="muted">
        У города нет дорожного слоя — сначала загрузите его выше, иначе вести линию не по чему.
      </p>
    )
  }

  return (
    <div className="route-drawing">
      {error && <ErrorBanner text={error} />}

      {/* Про результат текста нет намеренно: на карте видно и проложенную
          линию, и штрих рядом, а что делать дальше — написано на кнопках. */}
      {!result && (
        <p className="muted">
          {paused ? (
            'Рисование остановлено, линия сохранена на карте. «Подтвердить» — проложить её по дорогам, «Продолжить» — дорисовать дальше.'
          ) : (
            <>
              Ведите линию мышью с зажатой левой кнопкой — или ставьте клики там, где вести
              неудобно. Кнопку можно отпускать: линия продолжится с того места, где вы
              остановились. Колесо приближает, средняя кнопка двигает карту, у края она едет сама.
              Точно попадать в дорогу не нужно, но между двумя кликами маршрут пойдёт кратчайшим
              путём — поэтому клик на каждом повороте и хотя бы раз в пару кварталов.
            </>
          )}
        </p>
      )}

      <RouteMap
        // Пока результата нет — под рукой лежит прежняя линия маршрута, чтобы
        // было по чему ориентироваться. После — новая, ради которой всё и было.
        roads={current.roads}
        routes={result ? [result] : current.existing ? [current.existing] : []}
        colors={[route.color_hex ?? '#7dd3fc']}
        routeNames={[route.name]}
        hoveredIndex={result ? 0 : null}
        selectedIndex={null}
        onHoverChange={() => {}}
        onSelect={() => {}}
        zoomable
        drawing={!paused && !result}
        onSegmentDrawn={addSegment}
        stroke={stroke.length > 0 ? stroke : null}
      />

      <div className="route-drawing-actions">
        {result ? (
          <button
            type="button"
            className="primary"
            onClick={() => onSaved(`Линия маршрута «${route.name}» проложена по дорогам.`)}
          >
            Готово
          </button>
        ) : (
          <button
            type="button"
            className="primary"
            onClick={() => void confirm()}
            disabled={!canConfirm}
          >
            {saving ? 'Прокладываем…' : 'Подтвердить (Enter)'}
          </button>
        )}
        {!result &&
          (paused ? (
            <button type="button" className="ghost-button" onClick={() => setPaused(false)}>
              Продолжить
            </button>
          ) : (
            <button
              type="button"
              className="ghost-button"
              onClick={() => setPaused(true)}
              disabled={saving}
            >
              Остановить рисование (Esc)
            </button>
          ))}
        {!result && (
          <button type="button" className="ghost-button" onClick={undo} disabled={!canUndo}>
            Шаг назад (Ctrl+Z)
          </button>
        )}
        <button
          type="button"
          className="ghost-button"
          onClick={redraw}
          disabled={(segments.length === 0 && !result) || saving}
        >
          Перерисовать
        </button>
        {/* После сохранения отменять уже нечего: линия в базе. Оставить кнопку
            значило бы обещать откат, которого не будет. */}
        {!result && (
          <button
            type="button"
            className="ghost-button"
            onClick={() => onSaved('')}
            disabled={saving}
          >
            Отменить
          </button>
        )}
      </div>
    </div>
  )
}
