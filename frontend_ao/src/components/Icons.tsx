import type { ReactElement } from 'react'

export type IconKey =
  | 'dashboard'
  | 'users'
  | 'tenants'
  | 'sessions'
  | 'dossiers'
  | 'documents'
  | 'conversations'
  | 'check'
  | 'progress'
  | 'export'
  | 'exigence'
  | 'target'
  | 'compass'
  | 'audit'

const PATHS: Record<IconKey, ReactElement> = {
  dashboard: (
    <>
      <rect x="3.5" y="3.5" width="7" height="8" rx="1.5" />
      <rect x="13.5" y="3.5" width="7" height="5" rx="1.5" />
      <rect x="13.5" y="11.5" width="7" height="9" rx="1.5" />
      <rect x="3.5" y="14.5" width="7" height="6" rx="1.5" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 20c0-3.3 2.5-5.5 5.5-5.5s5.5 2.2 5.5 5.5" />
      <circle cx="17" cy="7.5" r="2.4" />
      <path d="M15.8 12.2c2.5.3 4.7 2.3 4.7 5.3" />
    </>
  ),
  tenants: (
    <>
      <path d="M4 20V6.5L12 3l8 3.5V20" />
      <path d="M4 20h16" />
      <path d="M9.5 20v-4.5h5V20" />
      <path d="M8 8.5h.01M12 8.5h.01M16 8.5h.01M8 12h.01M12 12h.01M16 12h.01" />
    </>
  ),
  sessions: (
    <>
      <circle cx="12" cy="12" r="8.2" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  dossiers: (
    <path d="M3.5 7.2c0-.94.76-1.7 1.7-1.7h4.2l1.8 2h7.6c.94 0 1.7.76 1.7 1.7v9.1c0 .94-.76 1.7-1.7 1.7H5.2c-.94 0-1.7-.76-1.7-1.7z" />
  ),
  documents: (
    <>
      <path d="M7 3.5h7l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-9A1.5 1.5 0 0 1 6 19V5A1.5 1.5 0 0 1 7 3.5Z" />
      <path d="M13.5 3.5V8h4.2" />
      <path d="M9 12.5h6M9 15.8h6M9 9.2h2" />
    </>
  ),
  conversations: (
    <>
      <path d="M4 5.5h16v10.2a1.3 1.3 0 0 1-1.3 1.3H9.8L5 20.5v-3.5H5.3A1.3 1.3 0 0 1 4 15.7Z" />
      <path d="M8 9.5h8M8 12.7h5" />
    </>
  ),
  check: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M8.2 12.3l2.5 2.5 5-5.2" />
    </>
  ),
  progress: (
    <>
      <path d="M4 18.5V13M9.3 18.5V8.5M14.6 18.5V11M20 18.5V5.5" />
    </>
  ),
  export: (
    <>
      <path d="M12 3.5v11" />
      <path d="M7.5 10.5 12 15l4.5-4.5" />
      <path d="M4.5 17v2A1.5 1.5 0 0 0 6 20.5h12a1.5 1.5 0 0 0 1.5-1.5v-2" />
    </>
  ),
  exigence: (
    <>
      <path d="M6 4h9l3.5 3.5V20H6Z" />
      <path d="M9 10.5h6M9 13.8h6M9 17h4" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8.3" />
      <circle cx="12" cy="12" r="4.6" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  compass: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m14.8 9.2-1.9 4.7-4.7 1.9 1.9-4.7z" />
    </>
  ),
  audit: (
    <>
      <path d="M12 3.5 5 6.2v5.3c0 4.7 3 8 7 9.5 4-1.5 7-4.8 7-9.5V6.2Z" />
      <path d="M9 12.3l2.2 2.2L15.5 10" />
    </>
  ),
}

export function Icon({ name, className }: { name: IconKey; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {PATHS[name]}
    </svg>
  )
}
