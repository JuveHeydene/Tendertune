import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import type { Role } from '../api/client'

const ROLE_LABEL: Record<Role, string> = {
  admin: 'Administration',
  manager: 'Direction AO',
  redacteur: 'Rédaction',
  consultant: 'Revue',
}

const NAV: Record<Role, { to: string; label: string; end?: boolean }[]> = {
  admin: [
    { to: '/app/admin', label: 'Tableau de bord', end: true },
    { to: '/app/admin/users', label: 'Utilisateurs' },
    { to: '/app/admin/tenants', label: 'Tenants' },
    { to: '/app/admin/sessions', label: 'Sessions' },
    // Manquait — trouvé en vérifiant la navigation réelle : sans ce lien,
    // aucune page dossier (liste ou détail 5 onglets) n'était joignable
    // pour ce rôle, seulement par URL directe.
    { to: '/app/dossiers', label: 'Dossiers AO' },
    { to: '/app/documents', label: 'Documents' },
    { to: '/app/conversations', label: 'Conversations' },
  ],
  manager: [
    { to: '/app/manager', label: 'Portefeuille', end: true },
    { to: '/app/dossiers', label: 'Dossiers AO' },
    { to: '/app/documents', label: 'Documents' },
    { to: '/app/conversations', label: 'Conversations' },
  ],
  redacteur: [
    { to: '/app/redacteur', label: 'Atelier', end: true },
    { to: '/app/dossiers', label: 'Dossiers' },
    { to: '/app/documents', label: 'Patrimoine' },
    { to: '/app/conversations', label: 'Conversations' },
  ],
  consultant: [
    { to: '/app/consultant', label: 'Revue', end: true },
    { to: '/app/dossiers', label: 'Dossiers' },
    { to: '/app/documents', label: 'Bibliothèque' },
    { to: '/app/conversations', label: 'Conversations' },
  ],
}

export function AppShell() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  if (!user) return null
  const links = NAV[user.role]

  async function onLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="logo">
          <span>CHANTIER</span>
          <strong>Offres</strong>
        </div>
        <p className="tenant">{user.tenant_name}</p>
        <nav>
          {links.map((l) => (
            <NavLink key={l.to + l.label} to={l.to} end={l.end}>
              {l.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <p className={`badge role-${user.role}`}>{ROLE_LABEL[user.role]}</p>
          <p className="who">
            {user.first_name} {user.last_name}
          </p>
          <button type="button" className="btn-ghost" onClick={onLogout}>
            Quitter le chantier
          </button>
        </div>
      </aside>
      <main className="main">
        <Outlet />
      </main>
    </div>
  )
}
