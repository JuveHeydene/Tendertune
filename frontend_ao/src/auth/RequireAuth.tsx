import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export function RequireAuth() {
  const { user, loading } = useAuth()
  if (loading) return <div className="boot">Ouverture du chantier…</div>
  if (!user) return <Navigate to="/login" replace />
  return <Outlet />
}
