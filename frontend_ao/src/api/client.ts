export type Role = 'admin' | 'manager' | 'redacteur' | 'consultant'

export type AuthUser = {
  id: string
  email: string
  username: string
  first_name: string | null
  last_name: string | null
  role: Role
  tenant_id: string
  tenant_slug: string
  tenant_name: string
}

export type LoginResponse = {
  access_token: string
  token_type: string
  user: AuthUser
}

export type DashboardSummary = {
  role: Role
  dossiers: number
  dossiers_en_cours: number
  documents_patrimoine: number
  documents_dao: number
  exigences_a_couvrir: number
  exports_count: number
  headline: string
  focus: string[]
}

export type Tenant = {
  id: string
  slug: string
  name: string
  email: string
  status: string
}

export type ManagedUser = AuthUser & {
  status: string
  last_login_at: string | null
}

export type UserSession = {
  id: string
  user_id: string
  email: string
  username: string
  user_agent: string | null
  expires_at: string
  last_activity_at: string
  revoked: boolean
  created_at: string
}

export type DocItem = {
  id: string
  tenant_id: string
  created_by: string | null
  filename: string
  doc_role: string
  doc_type: string | null
  is_dao: boolean
  dossier_origine_id: string | null
  status: string
  graph_extracted: boolean
  ingest_error: string | null
  object_key: string
  sha: string
  size_bytes: number | null
  mime_type: string | null
  ocr_used: boolean
  ocr_confidence: number | null
  page_count: number | null
  archived_at: string | null
  created_at: string | null
  updated_at: string | null
  duplicate?: boolean
}

export type Conversation = {
  id: string
  title: string | null
  dossier_id: string | null
  created_at: string
  updated_at: string
  messages?: {
    id: string
    role: string
    content: string
    created_at: string
    meta?: Record<string, unknown>
  }[]
  sections?: { key: string; title: string; status: string; markdown: string | null; excerpt?: string | null }[]
  preview_markdown?: string | null
  can_export?: boolean
}

export type ExportFormat = 'docx' | 'pdf' | 'md' | 'txt'

export type ExportItem = {
  id: string
  dossier_id: string
  project_name: string | null
  format: ExportFormat
  version: number
  size_bytes: number | null
  created_at: string
  download_name: string
}

export type Dossier = {
  id: string
  client_name: string | null
  project_name: string | null
  dao_reference: string | null
  status: string
  deadline: string | null
  current_version?: number | null
}

const TOKEN_KEY = 'btp_ao_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken()
  const headers = new Headers(init.headers)
  if (!(init.body instanceof FormData) && init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(path, { ...init, headers })
  const ctype = res.headers.get('content-type') || ''
  if (!res.ok) {
    let detail = res.statusText
    if (ctype.includes('application/json')) {
      try {
        const body = await res.json()
        if (typeof body.detail === 'string') detail = body.detail
      } catch {
        /* ignore */
      }
    } else if (ctype.includes('text/html')) {
      detail = `Réponse HTML (${res.status}) pour ${path} — proxy Vite / API manquant ?`
    }
    throw new Error(detail)
  }
  if (res.status === 204) return undefined as T
  if (!ctype.includes('application/json')) {
    throw new Error(`Réponse non-JSON pour ${path} — vérifier le proxy Vite (/exports, /documents…).`)
  }
  return res.json() as Promise<T>
}

export function login(email: string, password: string) {
  return request<LoginResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

export function fetchMe() {
  return request<AuthUser>('/auth/me')
}

export function logout() {
  return request<{ ok: boolean }>('/auth/logout', { method: 'POST' }).catch(() => ({ ok: true }))
}

export function fetchSummary() {
  return request<DashboardSummary>('/dashboard/summary')
}

export const adminApi = {
  tenants: () => request<Tenant[]>('/admin/tenants'),
  createTenant: (body: { slug: string; name: string; email: string }) =>
    request<Tenant>('/admin/tenants', { method: 'POST', body: JSON.stringify(body) }),
  patchTenant: (id: string, body: Partial<Tenant>) =>
    request<Tenant>(`/admin/tenants/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  users: () => request<ManagedUser[]>('/admin/users'),
  createUser: (body: Record<string, string>) =>
    request<ManagedUser>('/admin/users', { method: 'POST', body: JSON.stringify(body) }),
  patchUser: (id: string, body: Record<string, string | null>) =>
    request<ManagedUser>(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  sessions: () => request<UserSession[]>('/admin/sessions'),
  revokeSession: (id: string) =>
    request<{ ok: boolean }>(`/admin/sessions/${id}/revoke`, { method: 'POST' }),
  revokeUserSessions: (userId: string) =>
    request<{ ok: boolean; revoked: number }>(`/admin/users/${userId}/revoke-sessions`, {
      method: 'POST',
    }),
}

export const docsApi = {
  list: () => request<DocItem[]>('/documents'),
  get: (id: string) => request<DocItem>(`/documents/${id}`),
  upload: (file: File, docRole: string, docType: string) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('doc_role', docRole)
    if (docType) fd.append('doc_type', docType)
    return request<DocItem>('/documents', { method: 'POST', body: fd })
  },
  remove: (id: string) => request<void>(`/documents/${id}`, { method: 'DELETE' }),
}

export const exportsApi = {
  list: () => request<ExportItem[]>('/exports'),
  download: async (exportId: string, filename: string) => {
    const token = getToken()
    const headers = new Headers()
    if (token) headers.set('Authorization', `Bearer ${token}`)
    const res = await fetch(`/exports/${exportId}/download`, { headers })
    if (!res.ok) throw new Error(res.statusText || 'Téléchargement impossible')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  },
}

export const convApi = {
  list: () => request<Conversation[]>('/conversations'),
  create: (title?: string) =>
    request<Conversation>('/conversations', {
      method: 'POST',
      body: JSON.stringify({ title: title || null }),
    }),
  get: (id: string) => request<Conversation>(`/conversations/${id}`),
  rename: (id: string, title: string) =>
    request<Conversation>(`/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),
  remove: (id: string) => request<void>(`/conversations/${id}`, { method: 'DELETE' }),
  uploadDocument: (id: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<Conversation>(`/conversations/${id}/documents`, { method: 'POST', body: fd })
  },
  send: (id: string, text: string) =>
    request<Conversation>(`/conversations/${id}/messages`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  sendStream: async (
    id: string,
    text: string,
    handlers: {
      onToken?: (t: string) => void
      onPreview?: (md: string) => void
      onExportReady?: (format: ExportFormat, dossierId: string) => void
    },
  ) => {
    const token = getToken()
    const res = await fetch(`/conversations/${id}/messages/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify({ text }),
    })
    if (!res.ok) {
      let detail = res.statusText
      try {
        const body = await res.json()
        if (typeof body.detail === 'string') detail = body.detail
      } catch {
        /* ignore */
      }
      throw new Error(detail)
    }
    const reader = res.body?.getReader()
    if (!reader) throw new Error('Flux indisponible')
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const blocks = buf.split('\n\n')
      buf = blocks.pop() ?? ''
      for (const block of blocks) {
        let event = 'message'
        let dataLine = ''
        for (const line of block.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          if (line.startsWith('data:')) dataLine = line.slice(5).trim()
        }
        if (!dataLine) continue
        const data = JSON.parse(dataLine) as Record<string, unknown>
        if (event === 'token' && typeof data.t === 'string') handlers.onToken?.(data.t)
        if (event === 'preview' && typeof data.markdown === 'string') handlers.onPreview?.(data.markdown)
        if (event === 'export_ready' && typeof data.dossier_id === 'string') {
          handlers.onExportReady?.((data.format as ExportFormat) || 'docx', data.dossier_id)
        }
        if (event === 'error') throw new Error(String(data.message || 'Erreur serveur'))
      }
    }
  },
  exportDoc: (id: string, format: ExportFormat = 'docx') =>
    request<Conversation>(`/conversations/${id}/export`, {
      method: 'POST',
      body: JSON.stringify({ format }),
    }),
}

export function fetchDossiers() {
  return request<Dossier[]>('/dossiers')
}

export async function downloadDossierExport(dossierId: string, format: ExportFormat = 'docx') {
  const token = getToken()
  const headers = new Headers()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(`/dossiers/${dossierId}/export.${format}`, { headers })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `memoire-${dossierId.slice(0, 8)}.${format}`
  a.click()
  URL.revokeObjectURL(url)
}

/** @deprecated use downloadDossierExport */
export const downloadDossierDocx = (id: string) => downloadDossierExport(id, 'docx')
