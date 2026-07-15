export type Route =
  | { page: 'home' }
  | { page: 'runs' }
  | { page: 'new' }
  | { page: 'run'; runId: string }
  | { page: 'routes' }

export function currentRoute(): Route {
  if (window.location.pathname === '/') return { page: 'home' }
  if (window.location.pathname === '/routes') return { page: 'routes' }
  if (window.location.pathname === '/runs/new') return { page: 'new' }
  const match = window.location.pathname.match(/^\/runs\/([^/]+)$/)
  if (match) return { page: 'run', runId: match[1] }
  return { page: 'runs' }
}

export function navigate(path: string) {
  window.history.pushState({}, '', path)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

export function workspaceTitle(route: Route) {
  if (route.page === 'home') return 'Анализ заметности рекламы'
  if (route.page === 'new') return 'Загрузка видео'
  if (route.page === 'run') return 'Результат'
  if (route.page === 'routes') return 'Маршруты'
  return 'Архив'
}
