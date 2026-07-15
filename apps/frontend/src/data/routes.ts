export interface RouteMeta {
  id: string
  name: string
  colorLabel: string
  file: string
}

export interface CityRoutesData {
  routes: RouteMeta[]
  colors: string[]
}

export const CITY_ROUTES: Record<string, CityRoutesData> = {
  simferopol: {
    routes: [
      { id: 'route-1', name: 'Севастопольская | пр. Победы', colorLabel: 'Красная линия', file: 'route_1.geojson' },
      { id: 'route-2', name: 'Московская | Киевская', colorLabel: 'Синяя линия', file: 'route_2.geojson' },
      { id: 'route-3', name: 'Объездная дорога', colorLabel: 'Зелёная линия', file: 'route_3.geojson' },
      { id: 'route-4', name: 'Евпаторийское шоссе', colorLabel: 'Жёлтая линия', file: 'route_4.geojson' },
    ],
    colors: ['#ff3b3f', '#3b8cff', '#32c26b', '#f3c944'],
  },
}

export function findRoute(cityId: string, routeId: string): RouteMeta | undefined {
  return CITY_ROUTES[cityId]?.routes.find((route) => route.id === routeId)
}
