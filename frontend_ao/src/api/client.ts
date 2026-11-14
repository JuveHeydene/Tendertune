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

export type AuditLogEntry = {
  id: string
  tenant_id: string
  user_id: string | null
  user_email: string | null
  action_type: string
  resource_type: string | null
  resource_id: string | null
  details: Record<string, unknown>
  ip_address: string | null
  user_agent: string | null
  success: boolean
  error_message: string | null
  created_at: string
}

export type RetrievalTraceEntry = {
  sous_question_index: number
  sous_question_texte: string | null
  expert: string
  tentative: number
  query_utilisee: string
  filtres: Record<string, unknown>
  grade: string | null
  grade_method: string | null
  chunks_retournes: { chunk_id?: string; score?: number }[]
  abstention: boolean
  created_at: string
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
  dossier_id: string | null
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
  // { parse: { started_at, finished_at, error? }, chunk: {...}, classify: {...},
  //   embed: {...}, index: {...}, graph: {...} } — horodatage par phase du
  // pipeline d'ingestion, affiché dans le détail du document.
  pipeline_stages?: Record<string, { started_at?: string; finished_at?: string; error?: string }>
  // Nombre de pages déjà OCRisées et persistées (reprise après interruption).
  ocr_pages_done?: number
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
  has_dao: boolean
  dao_document_id: string | null
  dao_filename: string | null
  dao_status: string | null
  dao_ingest_error: string | null
  exigences_total: number
  exigences_couvertes: number
  exigences_eliminatoires_non_couvertes: number
  sections_total: number
  sections_approuvees: number
  classification_status: string | null
  classification_error: string | null
}

export type SectionExigenceLink = {
  exigence_id: string
  libelle: string
  type: string
  obligatoire: boolean
  statut_couverture: string
  origine: 'llm' | 'humain'
  statut_lien: 'proposee' | 'confirmee' | 'exclue'
  preuves_chunks: string[]
}

export type Exigence = {
  id: string
  libelle: string
  type: string
  obligatoire: boolean
  statut: 'a_couvrir' | 'en_cours' | 'couverte' | 'non_couverte' | 'a_revoir'
  reference_dao: string | null
  page_source: number | null
  preuves_chunks: string[]
}

export type ExigencePreuve = {
  chunk_id: string
  document_id: string | null
  document_filename: string | null
  page: number | null
  heading_path: string | null
  text: string
}

export type OutlineItemApi = {
  id: string
  key: string
  title: string
  heading_level: number
  sort_order: number
  status: 'todo' | 'generated' | 'approved' | 'rejected'
  archetype: 'institutionnelle' | 'factuelle' | 'narrative' | 'conformite'
}

export type SectionDetail = {
  section_key: string
  title: string
  status: string
  version: number | null
  markdown: string | null
  citations: unknown[]
  abstentions: string[]
  exigences_couvertes: string[]
}

export type ReviewApi = {
  id: string
  version: number
  action: 'approve' | 'edit' | 'regen'
  comment: string | null
  created_at: string
}

export type DossierPieceApi = {
  id: string
  libelle: string
  obligatoire: boolean
  statut: 'manquant' | 'trouve_patrimoine' | 'a_uploader' | 'fourni'
  document_id: string | null
  source: 'rc' | 'standard' | 'manuel'
}

const TOKEN_KEY = 'btp_ao_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
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
    throw new ApiError(detail, res.status)
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
  auditLogs: (filters?: { action_type?: string; resource_type?: string; success?: boolean }) => {
    const params = new URLSearchParams()
    if (filters?.action_type) params.set('action_type', filters.action_type)
    if (filters?.resource_type) params.set('resource_type', filters.resource_type)
    if (filters?.success !== undefined) params.set('success', String(filters.success))
    const qs = params.toString()
    return request<AuditLogEntry[]>(`/admin/audit-logs${qs ? `?${qs}` : ''}`)
  },
}

export const docsApi = {
  list: (dossierId?: string) =>
    request<DocItem[]>(dossierId ? `/documents?dossier_id=${dossierId}` : '/documents'),
  get: (id: string) => request<DocItem>(`/documents/${id}`),
  upload: (file: File, docRole: string, docType: string, dossierId?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('doc_role', docRole)
    if (docType) fd.append('doc_type', docType)
    if ((docRole === 'annexe' || docRole === 'dao_courant' || docRole === 'dao_archive') && dossierId) {
      fd.append('dossier_id', dossierId)
    }
    return request<DocItem>('/documents', { method: 'POST', body: fd })
  },
  promote: (id: string) => request<DocItem>(`/documents/${id}/promouvoir`, { method: 'POST' }),
  remove: (id: string) => request<void>(`/documents/${id}`, { method: 'DELETE' }),
  // Relance l'ingestion (reprend depuis la dernière page OCR connue, purge
  // les vecteurs Qdrant avant réindexation — aucun résidu dupliqué).
  relancerIngestion: (id: string) => request<DocItem>(`/documents/${id}/relancer-ingestion`, { method: 'POST' }),
  // Relance uniquement l'extraction du graphe (document déjà 'ready').
  relancerGraphe: (id: string) => request<DocItem>(`/documents/${id}/relancer-graphe`, { method: 'POST' }),
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
  create: (title?: string, dossierId?: string | null) =>
    request<Conversation>('/conversations', {
      method: 'POST',
      body: JSON.stringify({ title: title || null, dossier_id: dossierId || null }),
    }),
  get: (id: string) => request<Conversation>(`/conversations/${id}`),
  rename: (id: string, title: string) =>
    request<Conversation>(`/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),
  remove: (id: string) => request<void>(`/conversations/${id}`, { method: 'DELETE' }),
  messageTraces: (conversationId: string, messageId: string) =>
    request<RetrievalTraceEntry[]>(`/conversations/${conversationId}/messages/${messageId}/traces`),
  uploadDocument: (id: string, file: File, role: 'annexe' | 'patrimoine' = 'annexe') => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('role', role)
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

export async function downloadDossierPieces(dossierId: string, projectName?: string) {
  const token = getToken()
  const headers = new Headers()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(`/dossiers/${dossierId}/pieces/export`, { headers })
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
  a.download = `dossier_administratif_${(projectName || dossierId.slice(0, 8)).replace(/\s+/g, '_')}.pdf`
  a.click()
  URL.revokeObjectURL(url)
}

export const dossierApi = {
  list: () => request<Dossier[]>('/dossiers'),
  create: (body: { project_name: string; client_name?: string; dao_reference?: string; deadline?: string }) =>
    request<Dossier>('/dossiers', { method: 'POST', body: JSON.stringify(body) }),
  update: (
    id: string,
    body: Partial<{ project_name: string; client_name: string; dao_reference: string; deadline: string }>,
  ) => request<Dossier>(`/dossiers/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  get: (id: string) => request<Dossier>(`/dossiers/${id}`),
  analyser: (id: string) => request<{ dossier_id: string; status: string; job_id: string | null }>(
    `/dossiers/${id}/analyser`,
    { method: 'POST' },
  ),
  exigences: (id: string) => request<Exigence[]>(`/dossiers/${id}/exigences`),
  preuvesExigence: (dossierId: string, exigenceId: string) =>
    request<ExigencePreuve[]>(`/dossiers/${dossierId}/exigences/${exigenceId}/preuves`),
  relancerRechercheExigence: (dossierId: string, exigenceId: string) =>
    request<{ exigence_id: string; status: string }>(
      `/dossiers/${dossierId}/exigences/${exigenceId}/recherche`,
      { method: 'POST' },
    ),
  classifierSections: (dossierId: string) =>
    request<{ dossier_id: string; status: string; job_id: string | null }>(
      `/dossiers/${dossierId}/exigences/classifier-sections`,
      { method: 'POST' },
    ),
  sectionExigences: (dossierId: string, sectionKey: string) =>
    request<SectionExigenceLink[]>(`/dossiers/${dossierId}/sections/${sectionKey}/exigences`),
  linkSectionExigence: (dossierId: string, sectionKey: string, exigenceId: string) =>
    request<SectionExigenceLink>(`/dossiers/${dossierId}/sections/${sectionKey}/exigences/${exigenceId}`, {
      method: 'POST',
    }),
  confirmSectionExigence: (dossierId: string, sectionKey: string, exigenceId: string) =>
    request<SectionExigenceLink>(
      `/dossiers/${dossierId}/sections/${sectionKey}/exigences/${exigenceId}/confirmer`,
      { method: 'POST' },
    ),
  unlinkSectionExigence: (dossierId: string, sectionKey: string, exigenceId: string) =>
    request<void>(`/dossiers/${dossierId}/sections/${sectionKey}/exigences/${exigenceId}`, {
      method: 'DELETE',
    }),
  outline: (id: string) => request<OutlineItemApi[]>(`/dossiers/${id}/outline`),
  getSection: (dossierId: string, sectionKey: string) =>
    request<SectionDetail>(`/dossiers/${dossierId}/sections/${sectionKey}`),
  generateSection: (dossierId: string, sectionKey: string) =>
    request<SectionDetail>(`/dossiers/${dossierId}/sections/${sectionKey}/generate`, { method: 'POST' }),
  reviewSection: (
    dossierId: string,
    sectionKey: string,
    body: { action: 'approve' | 'edit' | 'regen'; text?: string; comment?: string },
  ) =>
    request<{ dossier_id: string; section_key: string; action: string; status: string }>(
      `/dossiers/${dossierId}/sections/${sectionKey}/review`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  historique: (dossierId: string, sectionKey: string) =>
    request<ReviewApi[]>(`/dossiers/${dossierId}/sections/${sectionKey}/historique`),
  sectionTraces: (dossierId: string, sectionKey: string) =>
    request<RetrievalTraceEntry[]>(`/dossiers/${dossierId}/sections/${sectionKey}/traces`),
  pieces: (id: string) => request<DossierPieceApi[]>(`/dossiers/${id}/pieces`),
  choisirPiece: (dossierId: string, pieceId: string, documentId: string) =>
    request<{ piece_id: string; statut: string }>(`/dossiers/${dossierId}/pieces/${pieceId}/choisir`, {
      method: 'POST',
      body: JSON.stringify({ document_id: documentId }),
    }),
  creerPiece: (dossierId: string, libelle: string, obligatoire = true) =>
    request<DossierPieceApi>(`/dossiers/${dossierId}/pieces`, {
      method: 'POST',
      body: JSON.stringify({ libelle, obligatoire }),
    }),
  retirerPiece: (dossierId: string, pieceId: string) =>
    request<void>(`/dossiers/${dossierId}/pieces/${pieceId}`, { method: 'DELETE' }),
  uploadPiece: (dossierId: string, pieceId: string, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return request<DossierPieceApi>(`/dossiers/${dossierId}/pieces/${pieceId}/upload`, {
      method: 'POST',
      body: fd,
    })
  },
}
