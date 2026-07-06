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
}

function isExternalLink(href: string | undefined): boolean {
  return /^https?:\/\//i.test(href || '')
}

const markdownComponents: Components = {
  a({ href, title, children }) {
    const external = isExternalLink(href)

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

export default function MarkdownRenderer({
  value,
  className,
  emptyPlaceholder = '暂无 Markdown 内容',
}: MarkdownRendererProps) {
  if (!value.trim()) {
    return (
      <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-neutral-800 bg-[#1A1A1A] text-sm text-neutral-600">
        {emptyPlaceholder}
      </div>
    )
  }

  return (
    <ReactMarkdown
      className={['markdown-body ai-markdown-renderer', className].filter(Boolean).join(' ')}
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeSlug, rehypeKatex]}
      components={markdownComponents}
    >
      {value}
    </ReactMarkdown>
  )
}
