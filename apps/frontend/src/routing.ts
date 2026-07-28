export interface VideoFilters {
  cityId?: string
  routeId?: string
  assignmentId?: string
  status?: string
  /** false — только видео без маршрута. */
  assigned?: boolean
}

export type Route =
  | { page: 'home' }
  | { page: 'archive' }
  | { page: 'catalog' }
  | { page: 'admin' }
  | { page: 'city'; citySlug: string }
  | { page: 'route'; citySlug: string; routeSlug: string }
  | { page: 'assignment'; assignmentId: string }
  | { page: 'videos'; filters: VideoFilters }
  | { page: 'upload'; citySlug?: string; routeSlug?: string; assignmentId?: string }
  | { page: 'run'; runId: string; seek?: number }

function parseVideoFilters(search: URLSearchParams): VideoFilters {
  const assigned = search.get('assigned')
  return {
    cityId: search.get('city') ?? undefined,
    routeId: search.get('route') ?? undefined,
    assignmentId: search.get('assignment') ?? undefined,
    status: search.get('status') ?? undefined,
    assigned: assigned === null ? undefined : assigned === 'true',
  }
}

export function currentRoute(): Route {
  const { pathname } = window.location
  const search = new URLSearchParams(window.location.search)

  if (pathname === '/') return { page: 'home' }
  if (pathname === '/archive') return { page: 'archive' }
  if (pathname === '/catalog') return { page: 'catalog' }
  if (pathname === '/admin') return { page: 'admin' }
  if (pathname === '/videos') return { page: 'videos', filters: parseVideoFilters(search) }
  if (pathname === '/upload') {
    return {
      page: 'upload',
      citySlug: search.get('city') ?? undefined,
      routeSlug: search.get('route') ?? undefined,
      assignmentId: search.get('assignment') ?? undefined,
    }
  }

  // Порядок важен: маршрут матчится раньше города.
  const routeMatch = pathname.match(/^\/archive\/([^/]+)\/([^/]+)$/)
  if (routeMatch) {
    return { page: 'route', citySlug: routeMatch[1], routeSlug: routeMatch[2] }
  }
  const cityMatch = pathname.match(/^\/archive\/([^/]+)$/)
  if (cityMatch) return { page: 'city', citySlug: cityMatch[1] }

  const assignmentMatch = pathname.match(/^\/assignments\/([^/]+)$/)
  if (assignmentMatch) return { page: 'assignment', assignmentId: assignmentMatch[1] }

  const runMatch = pathname.match(/^\/videos\/([^/]+)$/)
  if (runMatch) {
    const seek = Number(search.get('t'))
    return {
      page: 'run',
      runId: runMatch[1],
      seek: Number.isFinite(seek) && search.has('t') ? seek : undefined,
    }
  }

  return { page: 'archive' }
}

export function navigate(path: string) {
  window.history.pushState({}, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function videosPath(filters: VideoFilters = {}): string {
  const query = new URLSearchParams()
  if (filters.cityId) query.set('city', filters.cityId)
  if (filters.routeId) query.set('route', filters.routeId)
  if (filters.assignmentId) query.set('assignment', filters.assignmentId)
  if (filters.status) query.set('status', filters.status)
  if (filters.assigned !== undefined) query.set('assigned', String(filters.assigned))
  const suffix = query.toString()
  return suffix ? `/videos?${suffix}` : '/videos'
}

export function uploadPath(options: {
  citySlug?: string
  routeSlug?: string
  assignmentId?: string
} = {}): string {
  const query = new URLSearchParams()
  if (options.citySlug) query.set('city', options.citySlug)
  if (options.routeSlug) query.set('route', options.routeSlug)
  if (options.assignmentId) query.set('assignment', options.assignmentId)
  const suffix = query.toString()
  return suffix ? `/upload?${suffix}` : '/upload'
}

export function workspaceTitle(route: Route) {
  if (route.page === 'home') return 'Анализ заметности рекламы'
  if (route.page === 'upload') return 'Загрузка видео'
  if (route.page === 'run') return 'Результат'
  if (route.page === 'archive') return 'Города и маршруты'
  if (route.page === 'catalog') return 'Каталог конструкций'
  if (route.page === 'admin') return 'Админ-панель'
  if (route.page === 'city') return 'Маршруты города'
  if (route.page === 'route') return 'Задания маршрута'
  if (route.page === 'assignment') return 'Задание'
  return 'Все видео'
}
