import { Navigate, Route, Routes } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from './auth/AuthContext'
import { RequireAuth } from './auth/RequireAuth'
import { AppShell } from './layout/AppShell'
import { ConversationsLayout } from './layout/ConversationsLayout'
import { LoginPage } from './pages/LoginPage'
import { RoleDashboard } from './pages/RoleDashboard'
import { UsersPage } from './pages/admin/UsersPage'
import { TenantsPage } from './pages/admin/TenantsPage'
import { SessionsPage } from './pages/admin/SessionsPage'
import { DocumentsPage } from './pages/DocumentsPage'
import { ConversationThread } from './pages/ConversationsPage'
import { DossiersPage } from './pages/DossiersPage'
import type { Role } from './api/client'

function RoleGate({ role, children }: { role: Role; children: ReactNode }) {
  const { user } = useAuth()
  if (user && user.role !== role) return <Navigate to={`/app/${user.role}`} replace />
  return children
}

function AdminOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  if (user && user.role !== 'admin') return <Navigate to={`/app/${user.role}`} replace />
  return children
}

function HomeRedirect() {
  const { user, loading } = useAuth()
  if (loading) return <div className="boot">Ouverture du chantier…</div>
  if (!user) return <Navigate to="/login" replace />
  return <Navigate to={`/app/${user.role}`} replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<HomeRedirect />} />
      <Route element={<RequireAuth />}>
        <Route path="/app/conversations" element={<ConversationsLayout />}>
          <Route index element={<ConversationThread />} />
          <Route path="new" element={<ConversationThread />} />
          <Route path=":id" element={<ConversationThread />} />
        </Route>
        <Route path="/app" element={<AppShell />}>
          <Route
            path="admin"
            element={
              <RoleGate role="admin">
                <RoleDashboard />
              </RoleGate>
            }
          />
          <Route
            path="admin/users"
            element={
              <AdminOnly>
                <UsersPage />
              </AdminOnly>
            }
          />
          <Route
            path="admin/tenants"
            element={
              <AdminOnly>
                <TenantsPage />
              </AdminOnly>
            }
          />
          <Route
            path="admin/sessions"
            element={
              <AdminOnly>
                <SessionsPage />
              </AdminOnly>
            }
          />
          <Route
            path="manager"
            element={
              <RoleGate role="manager">
                <RoleDashboard />
              </RoleGate>
            }
          />
          <Route
            path="redacteur"
            element={
              <RoleGate role="redacteur">
                <RoleDashboard />
              </RoleGate>
            }
          />
          <Route
            path="consultant"
            element={
              <RoleGate role="consultant">
                <RoleDashboard />
              </RoleGate>
            }
          />
          <Route path="documents" element={<DocumentsPage />} />
          <Route path="dossiers" element={<DossiersPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
