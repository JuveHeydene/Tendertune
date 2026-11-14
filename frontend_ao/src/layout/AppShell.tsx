import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import type { Role } from '../api/client'
import { Icon, type IconKey } from '../components/Icons'

const ROLE_LABEL: Record<Role, string> = {
  admin: 'Administration',
  manager: 'Direction AO',
  redacteur: 'Rédaction',
  consultant: 'Revue',
}

type NavItem = { to: string; label: string; icon: IconKey; end?: boolean }

const NAV: Record<Role, NavItem[]> = {
  admin: [
    { to: '/app/admin', label: 'Tableau de bord', icon: 'dashboard', end: true },
    { to: '/app/admin/users', label: 'Utilisateurs', icon: 'users' },
    { to: '/app/admin/tenants', label: 'Tenants', icon: 'tenants' },
    { to: '/app/admin/sessions', label: 'Sessions', icon: 'sessions' },
    { to: '/app/admin/audit', label: "Journal d'audit", icon: 'audit' },
    { to: '/app/dossiers', label: 'Dossiers AO', icon: 'dossiers' },
    { to: '/app/documents', label: 'Documents', icon: 'documents' },
    { to: '/app/conversations', label: 'Conversations', icon: 'conversations' },
  ],
  manager: [
    { to: '/app/manager', label: 'Portefeuille', icon: 'dashboard', end: true },
    { to: '/app/dossiers', label: 'Dossiers AO', icon: 'dossiers' },
    { to: '/app/documents', label: 'Documents', icon: 'documents' },
    { to: '/app/conversations', label: 'Conversations', icon: 'conversations' },
  ],
  redacteur: [
    { to: '/app/redacteur', label: 'Atelier', icon: 'dashboard', end: true },
    { to: '/app/dossiers', label: 'Dossiers', icon: 'dossiers' },
    { to: '/app/documents', label: 'Patrimoine', icon: 'documents' },
    { to: '/app/conversations', label: 'Conversations', icon: 'conversations' },
  ],
  consultant: [
    { to: '/app/consultant', label: 'Revue', icon: 'dashboard', end: true },
    { to: '/app/dossiers', label: 'Dossiers', icon: 'dossiers' },
    { to: '/app/documents', label: 'Bibliothèque', icon: 'documents' },
    { to: '/app/conversations', label: 'Conversations', icon: 'conversations' },
  ],
}

function initials(first?: string | null, last?: string | null): string {
  const a = (first || '').trim()[0] || ''
  const b = (last || '').trim()[0] || ''
  return (a + b).toUpperCase() || '?'
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
          <span className="logo-mark" aria-hidden="true">CO</span>
          <span className="logo-text">
            <span className="logo-kicker">CHANTIER</span>
            <strong>Offres</strong>
          </span>
        </div>
        <p className="tenant" title={user.tenant_name}>
          {user.tenant_name}
        </p>
        <nav>
          {links.map((l) => (
            <NavLink key={l.to + l.label} to={l.to} end={l.end} title={l.label}>
              <Icon name={l.icon} className="nav-icon" />
              <span className="nav-label">{l.label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="who-card">
            <span className="avatar" aria-hidden="true">
              {initials(user.first_name, user.last_name)}
            </span>
            <span className="who-info">
              <span className="who-name">
                {user.first_name} {user.last_name}
              </span>
              <span className={`badge role-${user.role}`}>{ROLE_LABEL[user.role]}</span>
            </span>
          </div>
          <button type="button" className="btn-ghost logout-btn" onClick={onLogout}>
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
