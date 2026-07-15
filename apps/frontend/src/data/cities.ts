export interface CityMeta {
  id: string
  name: string
  region: string
  routeCount: number
}

export const CITIES: CityMeta[] = [
  { id: 'simferopol', name: 'Симферополь', region: 'Республика Крым', routeCount: 4 },
]

export function findCity(id: string): CityMeta | undefined {
  return CITIES.find((city) => city.id === id)
}
