import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

type Props = {
  markdown: string
  streaming?: boolean
  variant?: 'chat' | 'document'
  emptyLabel?: string
}

export function MarkdownPreview({
  markdown,
  streaming = false,
  variant = 'document',
  emptyLabel,
}: Props) {
  if (!markdown && !streaming) {
    return (
      <p className="muted preview-empty">
        {emptyLabel ?? 'Rien à afficher pour le moment.'}
      </p>
    )
  }
  return (
    <div
      className={[
        'md-preview',
        variant === 'document' ? 'md-preview--document' : 'md-preview--chat',
        streaming ? 'md-preview--live' : '',
      ]
        .filter(Boolean)
        .join(' ')}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown || ' '}</ReactMarkdown>
    </div>
  )
}
