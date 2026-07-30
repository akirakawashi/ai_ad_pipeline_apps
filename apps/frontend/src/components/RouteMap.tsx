import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent as ReactPointerEvent } from 'react'

type Position = [number, number]

interface GeoGeometry {
  type: string
  coordinates: unknown
}

export interface GeoFeature {
  type: 'Feature'
  properties?: Record<string, unknown>
  geometry: GeoGeometry
}

export interface GeoFeatureCollection {
  type: 'FeatureCollection'
  features: GeoFeature[]
}

interface Projector {
  project: (coordinate: Position) => Position
  unproject: (point: Position) => Position
}

const VIEWBOX = { width: 1420, height: 1085, padding: 55 }

/** Пределы приближения. Единица — вся карта в кадре, 40 — примерно квартал. */
const ZOOM_MIN = 1
const ZOOM_MAX = 40

/** Полоса у края кадра, в которой карта едет сама, пока ведёшь линию. */
const EDGE_BAND_PX = 48
const EDGE_SPEED_PX = 12

function toWebMercator([lon, lat]: Position): Position {
  const safeLat = Math.max(-85.05112878, Math.min(85.05112878, lat))
  const lonRadians = (lon * Math.PI) / 180
  const latRadians = (safeLat * Math.PI) / 180
  return [lonRadians, Math.log(Math.tan(Math.PI / 4 + latRadians / 2))]
}

function fromWebMercator([x, y]: Position): Position {
  return [(x * 180) / Math.PI, ((2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180) / Math.PI]
}

function collectCoordinates(collection: GeoFeatureCollection): Position[] {
  return collection.features.flatMap((feature) => {
    const geometry = feature.geometry
    if (!geometry) return []
    if (geometry.type === 'LineString') return geometry.coordinates as Position[]
    if (geometry.type === 'MultiLineString') return (geometry.coordinates as Position[][]).flat()
    return []
  })
}

function createProjector(collections: GeoFeatureCollection[]): Projector {
  const coords = collections.flatMap(collectCoordinates)
  const mercatorCoords = coords.map(toWebMercator)
  const xs = mercatorCoords.map(([x]) => x)
  const ys = mercatorCoords.map(([, y]) => y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)

  const innerWidth = VIEWBOX.width - VIEWBOX.padding * 2
  const innerHeight = VIEWBOX.height - VIEWBOX.padding * 2
  const xSpan = maxX - minX || 1
  const ySpan = maxY - minY || 1
  const scale = Math.min(innerWidth / xSpan, innerHeight / ySpan)
  const usedWidth = xSpan * scale
  const usedHeight = ySpan * scale
  const xOffset = (VIEWBOX.width - usedWidth) / 2
  const yOffset = (VIEWBOX.height - usedHeight) / 2

  return {
    project: (coordinate: Position) => {
      const [mercatorX, mercatorY] = toWebMercator(coordinate)
      return [xOffset + (mercatorX - minX) * scale, yOffset + (maxY - mercatorY) * scale]
    },
    // Обратный ход нужен рисованию: рука ведёт линию в координатах картинки, а
    // на сервер уходят долгота и широта. Без него штрих остался бы пикселями.
    unproject: ([x, y]: Position) =>
      fromWebMercator([minX + (x - xOffset) / scale, maxY - (y - yOffset) / scale]),
  }
}

function pointsToPath(points: Position[]): string {
  return points
    .map(([x, y], index) => `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`)
    .join(' ')
}

function lineStringToPath(coordinates: Position[], project: Projector['project']): string {
  return pointsToPath(coordinates.map(project))
}

function roadClass(properties: Record<string, unknown> = {}): string {
  const highway = (properties.highway as string) || (properties.class as string) || 'tertiary'
  if (highway === 'primary' || highway === 'primary_link') return 'primary'
  if (highway === 'secondary' || highway === 'secondary_link') return 'secondary'
  return 'tertiary'
}

/**
 * Линии маршрута → пути для отрисовки, в том порядке, в каком они лежат.
 *
 * Раньше здесь стояла раскладка кусков «ближайший конец от самой западной
 * точки»: маршрут приходил из OSM мешком отрезков без порядка, и по-другому
 * прочесть его было нельзя. Нарисованный маршрут упорядочен по построению —
 * это одна линия от начала до конца, — поэтому эвристика удалена вместе с
 * загрузкой geojson. Мешок (маршруты, нарисованные до перехода) тоже рисуется:
 * просто каждый кусок отдельным путём, как и был.
 */
function routePaths(features: GeoFeature[], project: Projector['project']): string[] {
  return features
    .filter((feature) => feature.geometry?.type === 'LineString')
    .map((feature) => lineStringToPath(feature.geometry.coordinates as Position[], project))
}

interface RouteVar extends CSSProperties {
  '--route-color'?: string
}

/** Точка каталога на карте: щит и сколько поверхностей в этом месте. */
export interface MapStructure {
  latitude: number
  longitude: number
  address: string
  surfaces_count: number
}

interface ViewBox {
  x: number
  y: number
  width: number
  height: number
}

const FULL_VIEW: ViewBox = { x: 0, y: 0, width: VIEWBOX.width, height: VIEWBOX.height }

export interface RouteMapProps {
  roads: GeoFeatureCollection
  routes: GeoFeatureCollection[]
  structures?: MapStructure[]
  colors: string[]
  routeNames: string[]
  hoveredIndex: number | null
  selectedIndex: number | null
  onHoverChange: (index: number | null) => void
  onSelect: (index: number) => void
  /** Колесо приближает, перетаскивание двигает. По умолчанию карта неподвижна. */
  zoomable?: boolean
  /**
   * Режим рисования: перетаскивание ведёт линию вместо панорамирования.
   * Готовый штрих отдаётся в onStrokeDrawn как пары [долгота, широта].
   */
  drawing?: boolean
  onStrokeDrawn?: (stroke: Position[]) => void
  /** Сырая линия «как вела рука» — показывается, пока её не подтвердили. */
  stroke?: Position[] | null
}

export function RouteMap({
  roads,
  routes,
  structures = [],
  colors,
  routeNames,
  hoveredIndex,
  selectedIndex,
  onHoverChange,
  onSelect,
  zoomable = false,
  drawing = false,
  onStrokeDrawn,
  stroke = null,
}: RouteMapProps) {
  const projector = useMemo(() => createProjector([roads, ...routes]), [roads, routes])
  const project = projector.project
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [view, setView] = useState<ViewBox>(FULL_VIEW)

  // Дорожный слой — до полутора тысяч линий, и он неподвижен: приближение и
  // панорамирование меняют viewBox, а не пути. Держим готовое дерево элементов,
  // иначе каждый кадр жеста пересобирал бы его заново.
  const roadLayer = useMemo(
    () => (
      <g>
        {roads.features
          .filter((feature) => feature.geometry?.type === 'LineString')
          .map((feature, index) => (
            <path
              key={index}
              d={lineStringToPath(feature.geometry.coordinates as Position[], project)}
              className={`road-path ${roadClass(feature.properties)}`}
            />
          ))}
      </g>
    ),
    [roads, project],
  )

  const routeSegments = useMemo(
    () => routes.map((route) => routePaths(route.features, project)),
    [routes, project],
  )

  const strokePath = useMemo(
    () => (stroke && stroke.length > 1 ? lineStringToPath(stroke, project) : null),
    [stroke, project],
  )

  // Точки каталога рисуем той же проекцией, что и дороги: библиотека карт не
  // нужна. Радиус растёт от числа поверхностей — иначе десять щитов в одной
  // точке визуально не отличить от одного.
  const structurePoints = useMemo(
    () =>
      structures.map((structure) => {
        const [x, y] = project([structure.longitude, structure.latitude])
        return {
          x,
          y,
          radius: 3 + Math.min(4, Math.sqrt(Math.max(1, structure.surfaces_count)) - 1),
          title:
            structure.surfaces_count > 1
              ? `${structure.address} — поверхностей: ${structure.surfaces_count}`
              : structure.address,
        }
      }),
    [structures, project],
  )

  /** Точка события в координатах картинки, с поправкой на текущий кадр. */
  const toUserSpace = useCallback(
    (clientX: number, clientY: number, box: ViewBox): Position | null => {
      const svg = svgRef.current
      if (!svg) return null
      const rect = svg.getBoundingClientRect()
      if (!rect.width || !rect.height) return null
      return [
        box.x + ((clientX - rect.left) / rect.width) * box.width,
        box.y + ((clientY - rect.top) / rect.height) * box.height,
      ]
    },
    [],
  )

  const clampView = useCallback((box: ViewBox): ViewBox => {
    const width = Math.min(
      VIEWBOX.width / ZOOM_MIN,
      Math.max(VIEWBOX.width / ZOOM_MAX, box.width),
    )
    const height = width * (VIEWBOX.height / VIEWBOX.width)
    return {
      width,
      height,
      x: Math.min(Math.max(0, box.x), VIEWBOX.width - width),
      y: Math.min(Math.max(0, box.y), VIEWBOX.height - height),
    }
  }, [])

  const handleWheel = useCallback(
    (event: WheelEvent) => {
      if (!zoomable) return
      event.preventDefault()
      setView((current) => {
        const anchor = toUserSpace(event.clientX, event.clientY, current)
        if (!anchor) return current
        const factor = Math.exp(event.deltaY * 0.0015)
        const width = current.width * factor
        const clamped = clampView({ ...current, width })
        // Точка под курсором остаётся под курсором: приближаемся туда, куда
        // смотрим, а не в центр кадра.
        const ratioX = (anchor[0] - current.x) / current.width
        const ratioY = (anchor[1] - current.y) / current.height
        return clampView({
          ...clamped,
          x: anchor[0] - ratioX * clamped.width,
          y: anchor[1] - ratioY * clamped.height,
        })
      })
    },
    [zoomable, toUserSpace, clampView],
  )

  // Колесо вешаем нативно, а не через onWheel. React отдаёт wheel **пассивным**
  // слушателем на корне, поэтому preventDefault() внутри onWheel молча не
  // срабатывает: карта приближалась бы, но страница под ней продолжала бы
  // прокручиваться. Отсюда и passive: false — только так прокрутку удаётся
  // остановить, пока курсор над картой.
  useEffect(() => {
    const svg = svgRef.current
    if (!svg || !zoomable) return
    svg.addEventListener('wheel', handleWheel, { passive: false })
    return () => svg.removeEventListener('wheel', handleWheel)
  }, [zoomable, handleWheel])

  // --- рисование и панорамирование -----------------------------------------
  // Оба живут на одних и тех же событиях указателя, поэтому и состояние одно.
  const gesture = useRef<
    | { kind: 'pan'; lastClient: Position }
    | { kind: 'draw'; points: Position[] }
    | null
  >(null)
  const edgePush = useRef<Position>([0, 0])
  // Линия, которую рука ведёт прямо сейчас, рисуется в обход React: атрибут
  // пути ставится напрямую по ссылке. Через состояние каждое движение мыши
  // перерисовывало бы полторы тысячи путей дорожного слоя.
  const livePathRef = useRef<SVGPathElement | null>(null)

  const showLiveStroke = useCallback((points: Position[]) => {
    livePathRef.current?.setAttribute('d', points.length > 1 ? pointsToPath(points) : '')
  }, [])

  // Карта едет сама, когда рука с линией подходит к краю кадра. Без этого
  // сорокакилометровый маршрут пришлось бы вести через двадцать экранов, не
  // отпуская кнопку, — то есть никак.
  useEffect(() => {
    if (!drawing) return
    let frame = 0
    const step = () => {
      const [pushX, pushY] = edgePush.current
      if (pushX || pushY) {
        setView((current) => {
          const scale = current.width / VIEWBOX.width
          return clampView({
            ...current,
            x: current.x + pushX * scale,
            y: current.y + pushY * scale,
          })
        })
      }
      frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [drawing, clampView])

  const handlePointerDown = (event: ReactPointerEvent<SVGSVGElement>) => {
    // Средняя кнопка двигает карту всегда. Без неё во взведённом режиме
    // рисования подвинуть карту было бы нечем: левая кнопка занята линией, а
    // выбирать место надо до того, как начал вести.
    const pans = event.button === 1 || (event.button === 0 && !drawing)
    if (pans) {
      if (!zoomable) return
      event.preventDefault()
      event.currentTarget.setPointerCapture(event.pointerId)
      gesture.current = { kind: 'pan', lastClient: [event.clientX, event.clientY] }
      return
    }
    if (event.button !== 0 || !drawing) return
    const point = toUserSpace(event.clientX, event.clientY, view)
    if (!point) return
    event.currentTarget.setPointerCapture(event.pointerId)
    gesture.current = { kind: 'draw', points: [point] }
    showLiveStroke([point])
  }

  const handlePointerMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const active = gesture.current
    if (!active) return

    if (active.kind === 'pan') {
      const svg = svgRef.current
      if (!svg) return
      const rect = svg.getBoundingClientRect()
      const scale = view.width / rect.width
      const dx = (event.clientX - active.lastClient[0]) * scale
      const dy = (event.clientY - active.lastClient[1]) * scale
      active.lastClient = [event.clientX, event.clientY]
      setView((current) => clampView({ ...current, x: current.x - dx, y: current.y - dy }))
      return
    }

    const point = toUserSpace(event.clientX, event.clientY, view)
    if (!point) return
    const previous = active.points[active.points.length - 1]
    // Точки ближе полутора единиц картинки не несут информации, а на сорока
    // километрах их набегают десятки тысяч. Прореживание здесь дешевле, чем
    // разбор такого тела на сервере.
    if (Math.hypot(point[0] - previous[0], point[1] - previous[1]) >= 1.5) {
      active.points.push(point)
      showLiveStroke(active.points)
    }

    const svg = svgRef.current
    if (svg) {
      const rect = svg.getBoundingClientRect()
      const left = event.clientX - rect.left
      const top = event.clientY - rect.top
      edgePush.current = [
        left < EDGE_BAND_PX ? -EDGE_SPEED_PX : left > rect.width - EDGE_BAND_PX ? EDGE_SPEED_PX : 0,
        top < EDGE_BAND_PX ? -EDGE_SPEED_PX : top > rect.height - EDGE_BAND_PX ? EDGE_SPEED_PX : 0,
      ]
    }
  }

  const finishGesture = (event: ReactPointerEvent<SVGSVGElement>) => {
    const active = gesture.current
    gesture.current = null
    edgePush.current = [0, 0]
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    if (active?.kind !== 'draw') return
    showLiveStroke([])
    if (active.points.length < 2) return
    onStrokeDrawn?.(active.points.map((point) => projector.unproject(point)))
  }

  const introSegmentRefs = useRef<SVGPathElement[][]>([])
  const introGroupRefs = useRef<(SVGGElement | null)[]>([])
  const drawTimers = useRef<number[]>([])

  useEffect(() => {
    if (hoveredIndex === null) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const paths = introSegmentRefs.current[hoveredIndex] ?? []
    const group = introGroupRefs.current[hoveredIndex]
    if (!paths.length || !group) return

    window.clearTimeout(drawTimers.current[hoveredIndex])

    const lengths = paths.map((path) => path.getTotalLength())
    const totalLength = lengths.reduce((total, length) => total + length, 0) || 1
    let elapsed = 0

    group.classList.remove('is-drawing')

    paths.forEach((path, index) => {
      const duration = Math.max(2, 200 * (lengths[index] / totalLength))
      path.style.strokeDasharray = `${lengths[index]}`
      path.style.strokeDashoffset = `${lengths[index]}`
      path.style.setProperty('--segment-delay', `${elapsed}ms`)
      path.style.setProperty('--segment-duration', `${duration}ms`)
      elapsed += duration
    })

    void group.getBoundingClientRect() // restart the CSS animation on each new hover
    group.classList.add('is-drawing')

    drawTimers.current[hoveredIndex] = window.setTimeout(() => {
      paths.forEach((path) => {
        path.style.strokeDashoffset = '0'
      })
      group.classList.remove('is-drawing')
    }, elapsed)
  }, [hoveredIndex])

  const focusedIndex = hoveredIndex ?? selectedIndex

  return (
    <div className="map-viewport" aria-label="Схема маршрутов">
      <svg
        ref={svgRef}
        viewBox={`${view.x} ${view.y} ${view.width} ${view.height}`}
        role="img"
        aria-labelledby="routeMapTitle routeMapDesc"
        className={`${zoomable ? 'is-zoomable' : ''}${drawing ? ' is-drawing-mode' : ''}`}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={finishGesture}
        onPointerCancel={finishGesture}
      >
        <title id="routeMapTitle">Схема дорог и маршрутов</title>
        <desc id="routeMapDesc">Векторная карта с маршрутами, проложенными по экспортированным OSM-сегментам.</desc>
        <defs>
          <filter id="routeGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="7" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {roadLayer}

        {structurePoints.length > 0 && (
          <g className="structure-layer">
            {structurePoints.map((point, index) => (
              <circle key={index} cx={point.x} cy={point.y} r={point.radius}>
                <title>{point.title}</title>
              </circle>
            ))}
          </g>
        )}

        <g>
          {routeSegments.map((segments, routeIndex) => {
            const isFocused = focusedIndex === routeIndex
            const isMuted = focusedIndex !== null && !isFocused
            const style: RouteVar = { '--route-color': colors[routeIndex] }
            return (
              <path
                key={routeIndex}
                d={segments.join(' ')}
                className={`target-route-glow${isFocused ? ' is-hovered' : ''}${isMuted ? ' is-muted' : ''}`}
                style={style}
              />
            )
          })}
        </g>

        <g>
          {routeSegments.map((segments, routeIndex) => {
            const style: RouteVar = { '--route-color': colors[routeIndex] }
            return (
              <g
                key={routeIndex}
                ref={(el) => {
                  introGroupRefs.current[routeIndex] = el
                }}
                className={`target-route-intro${focusedIndex === routeIndex ? ' is-hovered' : ''}`}
                style={style}
              >
                {segments.map((d, segmentIndex) => (
                  <path
                    key={segmentIndex}
                    ref={(el) => {
                      const routeRefs = (introSegmentRefs.current[routeIndex] ??= [])
                      if (el) routeRefs[segmentIndex] = el
                    }}
                    d={d}
                    className="target-route-intro-segment"
                  />
                ))}
              </g>
            )
          })}
        </g>

        <g>
          {routeSegments.map((segments, routeIndex) => {
            const style: RouteVar = { '--route-color': colors[routeIndex] }
            return segments.map((d, segmentIndex) => (
              <path
                key={`${routeIndex}-${segmentIndex}`}
                d={d}
                className="target-route-path"
                style={style}
                data-route-index={routeIndex}
                tabIndex={segmentIndex === 0 ? 0 : -1}
                role="button"
                aria-label={routeNames[routeIndex]}
                onMouseEnter={() => onHoverChange(routeIndex)}
                onMouseLeave={(event) => {
                  const related = (event.relatedTarget as Element | null)?.closest?.('.target-route-path')
                  if (related?.getAttribute('data-route-index') === String(routeIndex)) return
                  onHoverChange(null)
                }}
                onFocus={() => onHoverChange(routeIndex)}
                onBlur={() => onHoverChange(null)}
                onClick={() => onSelect(routeIndex)}
              />
            ))
          })}
        </g>

        {/* Сырой штрих поверх всего: и тот, что рука ведёт прямо сейчас (его
            ставит showLiveStroke мимо React), и уже нарисованный, пока его не
            подтвердили. Видно, что нарисовано, а не только что получилось. */}
        <path ref={livePathRef} className="hand-stroke" />
        {strokePath && <path d={strokePath} className="hand-stroke is-settled" />}
      </svg>

      <div className="legend">
        <span>
          <i className="legend-line road" />
          Основные дороги
        </span>
        <span>
          <i className="legend-line route" />
          Доступные маршруты
        </span>
      </div>
    </div>
  )
}
