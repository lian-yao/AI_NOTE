import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import rehypeKatex from 'rehype-katex'
import rehypeSlug from 'rehype-slug'
import Zoom from 'react-medium-image-zoom'
import 'github-markdown-css/github-markdown-dark.css'
import 'katex/dist/katex.min.css'
import 'react-medium-image-zoom/dist/styles.css'

interface MarkdownRendererProps {
  value: string
  className?: string
  emptyPlaceholder?: string
  onSeekTimestamp?: (seconds: number) => void
}

function isExternalLink(href: string | undefined): boolean {
  return /^https?:\/\//i.test(href || '')
}

function secondsFromTimestamp(value: string | undefined): number | null {
  if (!value) return null
  const parts = value
    .trim()
    .split(':')
    .map(part => Number(part))

  if (parts.length < 2 || parts.length > 3 || parts.some(part => !Number.isFinite(part))) {
    return null
  }

  if (parts.length === 2) {
    const [minutes, seconds] = parts
    return minutes * 60 + seconds
  }

  const [hours, minutes, seconds] = parts
  return hours * 3600 + minutes * 60 + seconds
}

function timestampFromHref(href: string | undefined): number | null {
  if (!href) return null

  const trimmed = href.trim()
  const hashMatch = trimmed.match(/^#t=(\d+(?:\.\d+)?)$/i)
  if (hashMatch) return Number(hashMatch[1])

  const queryMatch = trimmed.match(/[?&#]t=(\d+(?:\.\d+)?)/i)
  if (queryMatch) return Number(queryMatch[1])

  const timestampMatch = trimmed.match(/^timestamp:(.+)$/i)
  if (timestampMatch) return secondsFromTimestamp(timestampMatch[1])

  return null
}

function linkifyTimestamps(text: string): string {
  const timestampRe =
    /(^|[^\d:#])(\[?)((?:\d{1,2}:)?\d{1,2}:\d{2})(?:\s*(?:-|~|–|—|至|到)\s*((?:\d{1,2}:)?\d{1,2}:\d{2}))?(\]?)(?![\d:])/g

  return text.replace(timestampRe, (match, prefix, _open, start, end) => {
    const seconds = secondsFromTimestamp(start)
    if (seconds == null) return match

    const label = end ? `${start} - ${end}` : start
    return `${prefix}[${label}](#t=${seconds})`
  })
}

function linkifyMarkdownTimestamps(markdown: string): string {
  const fencedBlockRe = /(```[\s\S]*?```|~~~[\s\S]*?~~~)/g
  const protectedInlineRe = /(`[^`\n]*`|!?\[[^\]\n]*\]\([^)]+\)|<[^>\n]+>|https?:\/\/[^\s)]+)/g

  return markdown
    .split(fencedBlockRe)
    .map(block => {
      if (block.startsWith('```') || block.startsWith('~~~')) return block

      return block
        .split(protectedInlineRe)
        .map(part => {
          if (
            part.startsWith('`') ||
            part.startsWith('[') ||
            part.startsWith('![') ||
            part.startsWith('<') ||
            /^https?:\/\//i.test(part)
          ) {
            return part
          }
          return linkifyTimestamps(part)
        })
        .join('')
    })
    .join('')
}

function createMarkdownComponents(onSeekTimestamp?: (seconds: number) => void): Components {
  return {
    a({ href, title, children }) {
      const timestamp = timestampFromHref(href)
      const external = isExternalLink(href)

      if (timestamp != null && onSeekTimestamp) {
        return (
          <a
            href={href}
            title={title || '跳转到视频时间'}
            className="ai-timestamp-link"
            onClick={event => {
              event.preventDefault()
              onSeekTimestamp(timestamp)
            }}
          >
            {children}
          </a>
        )
      }

      return (
        <a
          href={href}
          title={title}
          target={external ? '_blank' : undefined}
          rel={external ? 'noreferrer' : undefined}
        >
          {children}
        </a>
      )
    },
    img({ src, alt, title }) {
      if (!src) return null

      return (
        <Zoom zoomMargin={24}>
          <img
            src={src}
            alt={alt || ''}
            title={title}
            loading="lazy"
            referrerPolicy="no-referrer"
            className="max-h-[520px] rounded-lg border border-neutral-800 object-contain"
          />
        </Zoom>
      )
    },
    table({ children }) {
      return (
        <div className="custom-scrollbar my-4 overflow-x-auto">
          <table>{children}</table>
        </div>
      )
    },
    input({ type, checked, disabled }) {
      if (type === 'checkbox') {
        return (
          <input
            type="checkbox"
            checked={Boolean(checked)}
            disabled={disabled}
            readOnly
            className="accent-primary mr-2 align-middle"
          />
        )
      }

      return <input type={type} disabled={disabled} />
    },
    code({ inline, className, children }) {
      return (
        <code
          className={[
            className,
            inline
              ? 'rounded bg-neutral-800/80 px-1.5 py-0.5 text-[0.9em]'
              : 'block min-w-full rounded-none bg-transparent p-0 whitespace-pre',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          {children}
        </code>
      )
    },
  }
}

export default function MarkdownRenderer({
  value,
  className,
  emptyPlaceholder = '暂无 Markdown 内容',
  onSeekTimestamp,
}: MarkdownRendererProps) {
  if (!value.trim()) {
    return (
      <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-neutral-800 bg-[#1A1A1A] text-sm text-neutral-600">
        {emptyPlaceholder}
      </div>
    )
  }

  const renderedValue = onSeekTimestamp ? linkifyMarkdownTimestamps(value) : value
  const markdownComponents = createMarkdownComponents(onSeekTimestamp)

  return (
    <ReactMarkdown
      className={['markdown-body ai-markdown-renderer', className].filter(Boolean).join(' ')}
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeSlug, rehypeKatex]}
      components={markdownComponents}
    >
      {renderedValue}
    </ReactMarkdown>
  )
}
