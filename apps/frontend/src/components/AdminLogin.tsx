import { useState } from 'react'
import { signInAdmin } from '../api'
import { ErrorBanner } from './common/Feedback'
import { PageHeader } from './common/PageHeader'

/**
 * Вход в админ-панель. Форма своя, а не системное окно браузера, но проверяет
 * пару не она: `signInAdmin` спрашивает бэкенд и запоминает пароль, только если
 * тот ответил 204. Обойти форму бессмысленно — админские эндпоинты отдают 401
 * сами по себе.
 */
export function AdminLogin({ onSuccess }: { onSuccess: () => void }) {
  const [login, setLogin] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await signInAdmin(login.trim(), password)
      onSuccess()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="page admin-login-page">
      <PageHeader
        eyebrow="Админ-панель"
        title="Нужен пароль"
        description="Города, маршруты и геометрия правятся здесь. Доступ — по паролю."
      />
      {error && <ErrorBanner text={error} />}
      <form className="panel catalog-panel admin-login" onSubmit={submit}>
        <div className="geozone-fields">
          <label className="field">
            Логин
            <input
              className="text-input"
              autoComplete="username"
              value={login}
              disabled={busy}
              onChange={(event) => setLogin(event.target.value)}
            />
          </label>
          <label className="field">
            Пароль
            <input
              className="text-input"
              type="password"
              autoComplete="current-password"
              value={password}
              disabled={busy}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
        </div>
        <div className="geozone-form-actions">
          <button className="primary" type="submit" disabled={busy}>
            {busy ? 'Проверяем…' : 'Войти'}
          </button>
        </div>
      </form>
    </div>
  )
}
