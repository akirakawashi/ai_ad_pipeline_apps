import logoUrl from '../assets/aisigroup-logo.png'
import { navigate } from '../routing'

const proofPoints = [
  { label: 'Детекции', value: '6 128' },
  { label: 'Объекты', value: '62' },
  { label: 'Треки', value: '135' },
]

const workflow = [
  {
    title: 'Загрузка ролика',
    text: 'Файл уходит напрямую в MinIO, backend ставит задачу в очередь.',
  },
  {
    title: 'ML-анализ',
    text: 'Пайплайн находит рекламные поверхности, группирует объекты и определяет бренд.',
  },
  {
    title: 'Интерактивный результат',
    text: 'Графики, карточки объектов и видео связаны между собой по времени.',
  },
]

export function LandingPage() {
  return (
    <div className="page landing-page">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-copy">
          <div className="landing-logo-card">
            <img src={logoUrl} alt="АИСИ ГРУПП" />
          </div>
          <p className="landing-eyebrow">AI video audit</p>
          <h1 id="landing-title">AI Ad Pipeline</h1>
          <p className="landing-lead">
            Веб-система для анализа рекламы в видео маршрута: загружает ролик,
            находит рекламные объекты, определяет бренды и показывает
            проверяемые метрики на интерактивной странице результата.
          </p>
          <div className="landing-actions">
            <button className="primary" onClick={() => navigate('/runs/new')}>
              Добавить видео
            </button>
            <button className="secondary" onClick={() => navigate('/runs')}>
              Открыть архив
            </button>
          </div>
        </div>

        <div className="landing-product" aria-label="Пример результата анализа">
          <div className="landing-product-top">
            <span>VideoProject.mp4</span>
            <strong>Готово</strong>
          </div>
          <div className="landing-video-preview">
            <div className="landing-bbox landing-bbox-mts">
              <span>MTS 54%</span>
            </div>
            <div className="landing-bbox landing-bbox-miranda">
              <span>MIRANDA 3%</span>
            </div>
            <div className="landing-play">▶</div>
          </div>
          <div className="landing-proof-grid">
            {proofPoints.map((point) => (
              <div key={point.label}>
                <span>{point.label}</span>
                <strong>{point.value}</strong>
              </div>
            ))}
          </div>
          <div className="landing-chart">
            <div style={{ height: '74%' }} />
            <div style={{ height: '18%' }} />
            <div style={{ height: '58%' }} />
          </div>
        </div>
      </section>

      <section className="landing-workflow" aria-label="Как работает продукт">
        {workflow.map((item, index) => (
          <article className="landing-step-card" key={item.title}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <h2>{item.title}</h2>
            <p>{item.text}</p>
          </article>
        ))}
      </section>
    </div>
  )
}
