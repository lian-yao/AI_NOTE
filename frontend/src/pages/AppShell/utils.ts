import type { Markdown, Segment, Task } from '@/store/taskStore'

export type ShellView = 'generate' | 'summary' | 'library' | 'settings'

export function getLatestMarkdown(markdown: Task['markdown'] | undefined): {
  content: string
  version?: Markdown
} {
  if (!markdown) return { content: '' }
  if (typeof markdown === 'string') return { content: markdown }

  const latest = [...markdown].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )[0]

  return {
    content: latest?.content || '',
    version: latest,
  }
}

export function getTaskTitle(task: Task | null | undefined): string {
  return task?.audioMeta?.title || task?.formData?.video_url || '未命名笔记'
}

export function getTaskAuthor(task: Task | null | undefined): string {
  return (
    task?.audioMeta?.raw_info?.uploader ||
    task?.audioMeta?.raw_info?.owner?.name ||
    task?.audioMeta?.raw_info?.author ||
    ''
  )
}

export function getTaskCoverUrl(task: Task | null | undefined): string {
  const rawCover = task?.audioMeta?.cover_url
  if (!rawCover) return ''

  if (task?.audioMeta?.platform === 'local' || rawCover.startsWith('/')) {
    return rawCover
  }

  const apiBase = String(import.meta.env.VITE_API_BASE_URL || '/api')
    .replace(/\/$/, '')
    .replace(/\/api$/, '')
  return `${apiBase}/image_proxy?url=${encodeURIComponent(rawCover)}`
}

export function formatTime(seconds: number | undefined): string {
  const safeSeconds = Number.isFinite(seconds) ? Math.max(0, Number(seconds)) : 0
  const hours = Math.floor(safeSeconds / 3600)
  const minutes = Math.floor((safeSeconds % 3600) / 60)
  const secs = Math.floor(safeSeconds % 60)

  if (hours > 0) {
    return `${hours}:${minutes.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  return `${minutes}:${secs.toString().padStart(2, '0')}`
}

export function formatDate(value: string | undefined): string {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''

  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function groupSegments(segments: Segment[], groupSize = 8) {
  const groups: { start: number; end: number; segments: Segment[]; text: string }[] = []
  for (let index = 0; index < segments.length; index += groupSize) {
    const chunk = segments.slice(index, index + groupSize)
    if (!chunk.length) continue
    groups.push({
      start: chunk[0].start,
      end: chunk[chunk.length - 1].end,
      segments: chunk,
      text: chunk.map(segment => segment.text).join(' '),
    })
  }
  return groups
}
