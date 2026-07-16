import type { ReactNode } from 'react'

export function EmptyState({
  text,
  action,
}: {
  text: string
  action?: ReactNode
}) {
  return (
    <div className="empty-state">
      <span>{text}</span>
      {action && <div className="empty-action">{action}</div>}
    </div>
  )
}

export function ErrorBanner({ text }: { text: string }) {
  return <div className="error-banner">{text}</div>
}

/** Для валидации и подсказок: это не ошибка, стилям ошибки тут не место. */
export function InfoBanner({ text }: { text: string }) {
  return <div className="info-banner">{text}</div>
}
