import type { ReactNode } from 'react'
import { formatBytes } from '../../utils/formatters'

interface FileCardProps {
  file: File
  /** Статус-пилюля справа. */
  status?: ReactNode
  /** Действия справа, например «Убрать». */
  actions?: ReactNode
  /** Прогресс или текст ошибки под именем файла. */
  children?: ReactNode
}

export function FileCard({ file, status, actions, children }: FileCardProps) {
  return (
    <div className="file-card">
      <div className="file-card-icon">▶</div>
      <div>
        <strong>{file.name}</strong>
        <span>
          {formatBytes(file.size)} · {file.type || 'video'}
        </span>
        {children}
      </div>
      {status}
      {actions}
    </div>
  )
}
