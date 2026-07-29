import { useEffect, useState } from 'react'
import logoUrl from './assets/aisigroup-logo.png'
import markUrl from './assets/aisigroup-mark.png'
import { AssignmentPage } from './pages/AssignmentPage'
import { AdminPage } from './pages/AdminPage'
import { CatalogPage } from './pages/CatalogPage'
import { CitiesPage } from './pages/CitiesPage'
import { CityPage } from './pages/CityPage'
import { LandingPage } from './pages/LandingPage'
import { RoutePage } from './pages/RoutePage'
import { RunPage } from './pages/RunPage'
import { UploadPage } from './pages/UploadPage'
import { VideosPage } from './pages/VideosPage'
import {
  currentRoute,
  navigate,
  uploadPath,
  type Route,
} from './routing'
import './App.css'

function backlink(route: Route): { label: string; to: string } | null {
  if (route.page === 'run') {
    return { label: '← Назад к видео', to: '/videos' }
  }
  if (route.page === 'upload') {
    return route.citySlug
      ? { label: '← Назад к маршруту', to: `/archive/${route.citySlug}` }
      : { label: '← Назад к видео', to: '/videos' }
  }
  if (route.page === 'city') {
    return { label: '← Назад к городам', to: '/archive' }
  }
  if (route.page === 'route') {
    return { label: '← Назад к городу', to: `/archive/${route.citySlug}` }
  }
  return null
}

function App() {
  const [route, setRoute] = useState<Route>(currentRoute)

  useEffect(() => {
    const update = () => setRoute(currentRoute())
    window.addEventListener('popstate', update)
    return () => window.removeEventListener('popstate', update)
  }, [])

  const back = backlink(route)
  const archiveActive =
    route.page === 'archive' ||
    route.page === 'city' ||
    route.page === 'route' ||
    route.page === 'assignment'

  return (
    <div className="app-shell">
      <aside className="side-rail" aria-label="Навигация">
        <div className="rail-brand">
          <button onClick={() => navigate('/')} aria-label="На стартовую страницу">
            <img src={markUrl} alt="АИСИ ГРУПП" />
          </button>
        </div>
        <nav className="rail-nav">
          <button
            className={route.page === 'home' ? 'active' : ''}
            onClick={() => navigate('/')}
          >
            <span>⌂</span>
            Продукт
          </button>
          <button
            className={archiveActive ? 'active' : ''}
            onClick={() => navigate('/archive')}
          >
            <span>⚑</span>
            Города
          </button>
          <button
            className={route.page === 'catalog' ? 'active' : ''}
            onClick={() => navigate('/catalog')}
          >
            <span>▦</span>
            Каталог
          </button>
          <button
            className={route.page === 'videos' || route.page === 'run' ? 'active' : ''}
            onClick={() => navigate('/videos')}
          >
            <span>▦</span>
            Все видео
          </button>
        </nav>
      </aside>
      <div className="workspace">
        <header className="workspace-header">
          <div className="workspace-header-inner">
            <div className="topbar-left">
              <button
                className="topbar-logo"
                onClick={() => navigate('/')}
                aria-label="На стартовую страницу"
              >
                <img src={logoUrl} alt="АИСИ ГРУПП" />
              </button>
            </div>
            <div className="topbar-right">
              {/* Админ-панель убрана из левого меню намеренно: это не рабочий
                  инструмент, а служебный экран под паролем. В общем меню она
                  выглядела приглашением зайти. */}
              <button
                className={`ghost-button topbar-admin${
                  route.page === 'admin' ? ' is-active' : ''
                }`}
                onClick={() => navigate('/admin')}
              >
                ⚙ Админ-панель
              </button>
              <button
                className="primary topbar-upload"
                onClick={() => navigate(uploadPath())}
              >
                ↑ Загрузить видео
              </button>
            </div>
          </div>
        </header>
        <main className="workspace-main">
          {back && (
            <div className="workspace-backline">
              <button
                className="workspace-backlink"
                onClick={() => navigate(back.to)}
              >
                {back.label}
              </button>
            </div>
          )}
          {route.page === 'home' && <LandingPage />}
          {route.page === 'archive' && <CitiesPage />}
          {route.page === 'catalog' && <CatalogPage />}
          {route.page === 'admin' && <AdminPage />}
          {route.page === 'city' && (
            <CityPage key={route.citySlug} citySlug={route.citySlug} />
          )}
          {/* key без периода: смена окна не должна пересоздавать страницу —
              иначе сбрасывался бы выбор «среднее/медиана» и мигал бы весь
              экран. Период приезжает пропом, сводка перечитывается сама. */}
          {route.page === 'route' && (
            <RoutePage
              key={`${route.citySlug}/${route.routeSlug}`}
              citySlug={route.citySlug}
              routeSlug={route.routeSlug}
              period={route.period}
            />
          )}
          {route.page === 'assignment' && (
            <AssignmentPage key={route.assignmentId} assignmentId={route.assignmentId} />
          )}
          {route.page === 'videos' && (
            <VideosPage filters={route.filters} />
          )}
          {route.page === 'upload' && (
            <UploadPage
              key={`${route.citySlug ?? ''}/${route.routeSlug ?? ''}/${route.assignmentId ?? ''}`}
              citySlug={route.citySlug}
              routeSlug={route.routeSlug}
              assignmentId={route.assignmentId}
            />
          )}
          {route.page === 'run' && (
            <RunPage key={route.runId} runId={route.runId} seek={route.seek} />
          )}
        </main>
      </div>
    </div>
  )
}

export default App
