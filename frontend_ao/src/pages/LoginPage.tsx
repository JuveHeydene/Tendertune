import { FormEvent, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (user) return <Navigate to="/" replace />

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setBusy(true)
    try {
      const u = await login(email, password)
      navigate(`/app/${u.role}`, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connexion impossible')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-page">
      <div className="login-visual" aria-hidden>
        <div className="grid-lines" />
        <div className="crane" />
        <p className="login-brand">
          <span>CHANTIER</span>
          <strong>Offres</strong>
        </p>
        <p className="login-tagline">
          Capitaliser le patrimoine. Rédiger le DAO. Tracer chaque citation.
        </p>
      </div>
      <div className="login-panel">
        <p className="eyebrow">Espace sécurisé</p>
        <h1>Connexion au chantier d’offres</h1>
        <p className="lede">
          Email et mot de passe suffisent. Votre entreprise (isolation des dossiers et documents)
          est celle de votre compte : pas besoin de la choisir ici.
        </p>
        <form onSubmit={onSubmit} className="login-form">
          <label>
            Email
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </label>
          <label>
            Mot de passe
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error ? <p className="form-error">{error}</p> : null}
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? 'Vérification…' : 'Entrer sur le chantier'}
          </button>
        </form>
      </div>
    </div>
  )
}
