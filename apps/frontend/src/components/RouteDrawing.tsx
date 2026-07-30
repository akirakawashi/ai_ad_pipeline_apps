import { useEffect, useState } from 'react'

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
 * Попадать в дорогу точно не нужно: сервер кладёт линию на сеть сам, и промах
 * в пару десятков метров ничего не меняет.
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
  const [stroke, setStroke] = useState<Stroke | null>(null)
  // Проложенная линия, вернувшаяся с сервера. Пока она есть, экран показывает
  // результат, а не приглашает рисовать.
  const [result, setResult] = useState<GeoFeatureCollection | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const key = `${citySlug}/${route.slug}`
  const current = loaded?.key === key ? loaded : null

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

  const confirm = async () => {
    if (!stroke) return
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
  }

  const redraw = () => {
    setStroke(null)
    setResult(null)
    setError('')
  }

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
          {stroke
            ? 'Линия нарисована. «Подтвердить» — проложить её по дорогам и посмотреть, что вышло.'
            : 'Ведите линию по маршруту, не отпуская левую кнопку мыши. Колесо приближает, средняя кнопка двигает карту, у края она едет сама. Точно попадать в дорогу не нужно — линия ляжет на дороги сама.'}
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
        drawing={!stroke && !result}
        onStrokeDrawn={setStroke}
        stroke={stroke}
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
            onClick={confirm}
            disabled={!stroke || saving}
          >
            {saving ? 'Прокладываем…' : 'Подтвердить'}
          </button>
        )}
        <button
          type="button"
          className="ghost-button"
          onClick={redraw}
          disabled={(!stroke && !result) || saving}
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
