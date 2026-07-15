export function RunsSkeleton() {
  return (
    <div className="runs-grid skeleton-grid" aria-label="Загружаем архив">
      {Array.from({ length: 6 }).map((_, index) => (
        <div className="run-card skeleton-card" key={index}>
          <SkeletonBlock className="run-preview-skeleton" />
          <div className="run-copy">
            <SkeletonBlock className="skeleton-pill" />
            <SkeletonBlock className="skeleton-line wide" />
            <SkeletonBlock className="skeleton-line" />
          </div>
        </div>
      ))}
    </div>
  )
}

export function MetricSkeletonGrid() {
  return (
    <div className="summary-grid" aria-label="Загружаем метрики">
      {Array.from({ length: 4 }).map((_, index) => (
        <div className="metric-card skeleton-card" key={index}>
          <SkeletonBlock className="skeleton-line short" />
          <SkeletonBlock className="skeleton-value" />
        </div>
      ))}
    </div>
  )
}

export function PlayerSkeleton() {
  return (
    <section className="panel player-panel player-skeleton">
      <SkeletonBlock className="player-skeleton-frame" />
    </section>
  )
}

export function ChartsSkeleton() {
  return (
    <div className="charts-grid charts-skeleton" aria-label="Загружаем графики">
      <section className="panel chart-card skeleton-card">
        <SkeletonBlock className="skeleton-line wide" />
        <SkeletonBlock className="chart-skeleton-frame" />
      </section>
      <section className="panel chart-card skeleton-card">
        <SkeletonBlock className="skeleton-line wide" />
        <SkeletonBlock className="chart-skeleton-frame" />
      </section>
      <section className="panel chart-card timeline-chart skeleton-card">
        <SkeletonBlock className="skeleton-line wide" />
        <SkeletonBlock className="timeline-skeleton-frame" />
      </section>
    </div>
  )
}

export function ObjectsSkeleton() {
  return (
    <section
      className="panel objects-panel skeleton-card"
      aria-label="Загружаем объекты"
    >
      <header>
        <SkeletonBlock className="skeleton-line wide" />
        <SkeletonBlock className="skeleton-line" />
      </header>
      <div className="objects-grid">
        {Array.from({ length: 8 }).map((_, index) => (
          <div className="object-card object-skeleton-card" key={index}>
            <SkeletonBlock className="object-skeleton-image" />
            <SkeletonBlock className="skeleton-line wide" />
            <SkeletonBlock className="skeleton-line" />
          </div>
        ))}
      </div>
    </section>
  )
}

export function RouteMapSkeleton() {
  return (
    <div className="content-grid" aria-label="Загружаем маршруты">
      <section className="panel map-card skeleton-card">
        <SkeletonBlock className="route-map-skeleton-frame" />
      </section>
      <aside className="panel side-panel skeleton-card">
        <SkeletonBlock className="skeleton-line short" />
        <SkeletonBlock className="skeleton-value" />
        {Array.from({ length: 4 }).map((_, index) => (
          <SkeletonBlock className="route-option-skeleton" key={index} />
        ))}
      </aside>
    </div>
  )
}

function SkeletonBlock({ className = '' }: { className?: string }) {
  return <span className={`skeleton-block ${className}`} />
}
