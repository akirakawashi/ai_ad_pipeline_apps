import logoUrl from '../assets/aisigroup-logo.png'
import { navigate } from '../routing'

export function LandingPage() {
  return (
    <div className="page landing-page">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-copy">
          <div className="landing-logo-card">
            <img src={logoUrl} alt="АИСИ ГРУПП" />
          </div>
          <p className="landing-eyebrow">Видеоаналитика для бизнеса</p>
          <h1 id="landing-title">Анализ заметности рекламы</h1>
          <p className="landing-lead">
            Веб-система для анализа рекламы в видео маршрута: загружает ролик,
            находит рекламные объекты, определяет бренды и показывает
            проверяемые метрики на интерактивной странице результата.
          </p>
          <div className="landing-actions">
            <button className="primary" onClick={() => navigate('/upload')}>
              Загрузить видео
            </button>
            <button className="secondary" onClick={() => navigate('/archive')}>
              Города и маршруты
            </button>
            <button className="secondary" onClick={() => navigate('/videos')}>
              Все видео
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
