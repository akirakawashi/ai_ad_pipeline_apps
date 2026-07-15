import { useEffect, useState } from 'react'
import logoUrl from './assets/aisigroup-logo.png'
import markUrl from './assets/aisigroup-mark.png'
import { CitiesPage } from './pages/CitiesPage'
import { LandingPage } from './pages/LandingPage'
import { RoutesPage } from './pages/RoutesPage'
import { RunPage } from './pages/RunPage'
import { RunsPage } from './pages/RunsPage'
import { UploadPage } from './pages/UploadPage'
import {
  currentRoute,
  navigate,
  type Route,
} from './routing'
import './App.css'

function backlink(route: Route): { label: string; to: string } | null {
  if (route.page === 'new' || route.page === 'run') {
    return { label: '← Назад к архиву', to: '/runs' }
  }
  if (route.page === 'routes') {
    return { label: '← Назад к городам', to: '/routes' }
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
            className={route.page === 'runs' ? 'active' : ''}
            onClick={() => navigate('/runs')}
          >
            <span>▦</span>
            Архив
          </button>
          <button
            className={route.page === 'cities' || route.page === 'routes' ? 'active' : ''}
            onClick={() => navigate('/routes')}
          >
            <span>⚑</span>
            Маршруты
          </button>
          <button
            className={route.page === 'new' ? 'active' : ''}
            onClick={() => navigate('/runs/new')}
          >
            <span>↑</span>
            Новое видео
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
            <div className="topbar-status">
              <span />
              Сервис активен
            </div>
          </div>
        </header>
        <main className="workspace-main">
          {backlink(route) && (
            <div className="workspace-backline">
              <button
                className="workspace-backlink"
                onClick={() => navigate(backlink(route)!.to)}
              >
                {backlink(route)!.label}
              </button>
            </div>
          )}
          {route.page === 'home' && <LandingPage />}
          {route.page === 'runs' && <RunsPage />}
          {route.page === 'cities' && <CitiesPage />}
          {route.page === 'routes' && <RoutesPage key={route.cityId} cityId={route.cityId} />}
          {route.page === 'new' && <UploadPage />}
          {route.page === 'run' && <RunPage runId={route.runId} />}
        </main>
      </div>
    </div>
  )
}

export default App
