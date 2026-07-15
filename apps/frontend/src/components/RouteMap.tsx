import { useEffect, useMemo, useRef, type CSSProperties } from 'react'

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

type Projector = (coordinate: Position) => Position

const VIEWBOX = { width: 1420, height: 1085, padding: 55 }

function toWebMercator([lon, lat]: Position): Position {
  const safeLat = Math.max(-85.05112878, Math.min(85.05112878, lat))
  const lonRadians = (lon * Math.PI) / 180
  const latRadians = (safeLat * Math.PI) / 180
  return [lonRadians, Math.log(Math.tan(Math.PI / 4 + latRadians / 2))]
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

  return (coordinate: Position) => {
    const [mercatorX, mercatorY] = toWebMercator(coordinate)
    const x = xOffset + (mercatorX - minX) * scale
    const y = yOffset + (maxY - mercatorY) * scale
    return [x, y]
  }
}

function lineStringToPath(coordinates: Position[], project: Projector): string {
  return coordinates
    .map((coord, index) => {
      const [x, y] = project(coord)
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
    })
    .join(' ')
}

function roadClass(properties: Record<string, unknown> = {}): string {
  const highway = (properties.highway as string) || (properties.class as string) || 'tertiary'
  if (highway === 'primary' || highway === 'primary_link') return 'primary'
  if (highway === 'secondary' || highway === 'secondary_link') return 'secondary'
  return 'tertiary'
}

/** Orders disjoint OSM way segments into a single continuous drawing path, nearest-neighbor from the westernmost endpoint. */
function orderRouteSegments(features: GeoFeature[], project: Projector): string[] {
  const segments = features
    .filter((feature) => feature.geometry?.type === 'LineString')
    .map((feature) => ({ coordinates: feature.geometry.coordinates as Position[] }))

  if (!segments.length) return []

  const endpoints = segments.flatMap(({ coordinates }) => [coordinates[0], coordinates[coordinates.length - 1]])
  let cursor = endpoints.reduce((westernmost, point) =>
    project(point)[0] < project(westernmost)[0] ? point : westernmost,
  )
  const remaining = [...segments]
  const orderedPaths: string[] = []

  while (remaining.length) {
    let bestIndex = 0
    let shouldReverse = false
    let bestDistance = Infinity

    for (let index = 0; index < remaining.length; index += 1) {
      const { coordinates } = remaining[index]
      const start = project(coordinates[0])
      const end = project(coordinates[coordinates.length - 1])
      const cursorPoint = project(cursor)
      const startDistance = Math.hypot(start[0] - cursorPoint[0], start[1] - cursorPoint[1])
      const endDistance = Math.hypot(end[0] - cursorPoint[0], end[1] - cursorPoint[1])
      const distance = Math.min(startDistance, endDistance)

      if (distance < bestDistance) {
        bestIndex = index
        shouldReverse = endDistance < startDistance
        bestDistance = distance
      }
    }

    const [{ coordinates }] = remaining.splice(bestIndex, 1)
    const oriented = shouldReverse ? [...coordinates].reverse() : coordinates
    orderedPaths.push(lineStringToPath(oriented, project))
    cursor = oriented[oriented.length - 1]
  }

  return orderedPaths
}

interface RouteVar extends CSSProperties {
  '--route-color'?: string
}

export interface RouteMapProps {
  roads: GeoFeatureCollection
  routes: GeoFeatureCollection[]
  colors: string[]
  routeNames: string[]
  hoveredIndex: number | null
  selectedIndex: number | null
  onHoverChange: (index: number | null) => void
  onSelect: (index: number) => void
}

export function RouteMap({
  roads,
  routes,
  colors,
  routeNames,
  hoveredIndex,
  selectedIndex,
  onHoverChange,
  onSelect,
}: RouteMapProps) {
  const project = useMemo(() => createProjector([roads, ...routes]), [roads, routes])

  const roadPaths = useMemo(
    () =>
      roads.features
        .filter((feature) => feature.geometry?.type === 'LineString')
        .map((feature) => ({
          d: lineStringToPath(feature.geometry.coordinates as Position[], project),
          className: roadClass(feature.properties),
        })),
    [roads, project],
  )

  const routeSegments = useMemo(
    () => routes.map((route) => orderRouteSegments(route.features, project)),
    [routes, project],
  )

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
      <svg viewBox={`0 0 ${VIEWBOX.width} ${VIEWBOX.height}`} role="img" aria-labelledby="routeMapTitle routeMapDesc">
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

        <g>
          {roadPaths.map((road, index) => (
            <path key={index} d={road.d} className={`road-path ${road.className}`} />
          ))}
        </g>

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
