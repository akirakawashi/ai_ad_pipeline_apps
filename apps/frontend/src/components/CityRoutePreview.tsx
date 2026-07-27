import { useId, useMemo } from 'react'
import type { GeoFeatureCollection } from './RouteMap'

type Position = [number, number]

const VIEWBOX = { width: 320, height: 148, padding: 18 }

function toWebMercator([lon, lat]: Position): Position {
  const safeLat = Math.max(-85.05112878, Math.min(85.05112878, lat))
  const lonRadians = (lon * Math.PI) / 180
  const latRadians = (safeLat * Math.PI) / 180
  return [lonRadians, Math.log(Math.tan(Math.PI / 4 + latRadians / 2))]
}

function coordinatesFromRoutes(routes: GeoFeatureCollection[]): Position[] {
  return routes.flatMap((route) =>
    route.features.flatMap((feature) => {
      if (feature.geometry?.type === 'LineString') {
        return feature.geometry.coordinates as Position[]
      }
      if (feature.geometry?.type === 'MultiLineString') {
        return (feature.geometry.coordinates as Position[][]).flat()
      }
      return []
    }),
  )
}

function routePath(routes: GeoFeatureCollection[]): string {
  const coordinates = coordinatesFromRoutes(routes)
  if (!coordinates.length) return ''

  const mercatorCoordinates = coordinates.map(toWebMercator)
  const xs = mercatorCoordinates.map(([x]) => x)
  const ys = mercatorCoordinates.map(([, y]) => y)
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const innerWidth = VIEWBOX.width - VIEWBOX.padding * 2
  const innerHeight = VIEWBOX.height - VIEWBOX.padding * 2
  const scale = Math.min(
    innerWidth / (maxX - minX || 1),
    innerHeight / (maxY - minY || 1),
  )
  const usedWidth = (maxX - minX) * scale
  const usedHeight = (maxY - minY) * scale
  const xOffset = (VIEWBOX.width - usedWidth) / 2
  const yOffset = (VIEWBOX.height - usedHeight) / 2

  const project = (coordinate: Position): Position => {
    const [x, y] = toWebMercator(coordinate)
    return [xOffset + (x - minX) * scale, yOffset + (maxY - y) * scale]
  }

  const lineToPath = (line: Position[]) =>
    line
      .map((coordinate, index) => {
        const [x, y] = project(coordinate)
        return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`
      })
      .join(' ')

  return routes
    .flatMap((route) =>
      route.features.flatMap((feature) => {
        if (feature.geometry?.type === 'LineString') {
          return [lineToPath(feature.geometry.coordinates as Position[])]
        }
        if (feature.geometry?.type === 'MultiLineString') {
          return (feature.geometry.coordinates as Position[][]).map(lineToPath)
        }
        return []
      }),
    )
    .join(' ')
}

/** A compact, monochrome preview of the real route geometry stored for a city. */
export function CityRoutePreview({
  routes,
  className = '',
}: {
  routes: GeoFeatureCollection[] | null
  className?: string
}) {
  const filterId = useId().replace(/:/g, '')
  const path = useMemo(() => (routes ? routePath(routes) : ''), [routes])
  const loading = routes === null

  return (
    <svg
      className={`city-route-preview${loading ? ' is-loading' : ''}${
        className ? ` ${className}` : ''
      }`}
      viewBox={`0 0 ${VIEWBOX.width} ${VIEWBOX.height}`}
      aria-hidden="true"
    >
      <defs>
        <filter id={filterId} x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="3.8" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {path && (
        <>
          <path className="city-route-preview-glow" d={path} filter={`url(#${filterId})`} />
          <path className="city-route-preview-line" d={path} />
        </>
      )}
    </svg>
  )
}
