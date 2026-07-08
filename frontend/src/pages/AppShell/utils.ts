import type { Markdown, Segment, Task } from '@/store/taskStore'
import { getApiBaseURL } from '@/utils/api'

export type ShellView = 'generate' | 'summary' | 'library' | 'settings'

export interface TimelineSection {
  key: string
  title: string
  content: string
  startTime: number
  endTime: number
  screenshotUrl: string
}

export function getLatestMarkdown(markdown: Task['markdown'] | undefined): {
  content: string
  version?: Markdown
} {
  if (!markdown) return { content: '' }
  if (typeof markdown === 'string') return { content: markdown }

  const latest = [...markdown].sort(
    (a, b) =>
      (parseBackendDate(b.created_at)?.getTime() || 0) -
      (parseBackendDate(a.created_at)?.getTime() || 0)
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
  const rawInfo = task?.audioMeta?.raw_info
  if (!rawInfo || typeof rawInfo !== 'object') return ''

  const item = rawInfo as {
    uploader?: string
    owner?: { name?: string }
    author?: string
  }

  return item.uploader || item.owner?.name || item.author || ''
}

export function getTaskCoverUrl(task: Task | null | undefined): string {
  const rawCover = task?.audioMeta?.cover_url
  if (!rawCover) return ''

  return resolveDisplayImageUrl(rawCover, task?.audioMeta?.platform)
}

export function resolveDisplayImageUrl(rawUrl: string, platform = ''): string {
  if (!rawUrl) return ''

  if (rawUrl.startsWith('//')) {
    return resolveDisplayImageUrl(`https:${rawUrl}`, platform)
  }

  if (
    platform === 'local' ||
    rawUrl.startsWith('/') ||
    rawUrl.startsWith('data:') ||
    rawUrl.startsWith('blob:')
  ) {
    return rawUrl
  }

  const backendBase = getApiBaseURL()
    .replace(/\/+$/, '')
    .replace(/\/api\/v1$/i, '')
    .replace(/\/api$/i, '')
  return `${backendBase}/image_proxy?url=${encodeURIComponent(rawUrl)}`
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

export function parseTimestamp(value: string | undefined): number | null {
  if (!value) return null

  const parts = value
    .trim()
    .replace(/^\[|\]$/g, '')
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

function coerceTimestamp(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return Math.max(0, value)
  if (typeof value === 'string') return Math.max(0, parseTimestamp(value) || 0)
  return 0
}

function cleanSectionTitle(value: string): string {
  return value
    .replace(
      /[（(［[]\s*\d{1,2}:\d{2}(?::\d{2})?\s*(?:-|~|–|—|至|到)\s*\d{1,2}:\d{2}(?::\d{2})?\s*[）)］\]]/g,
      ''
    )
    .replace(/^章节\s*[一二三四五六七八九十百\d]+\s*[:：-]\s*/i, '')
    .replace(/^第[一二三四五六七八九十百\d]+(?:章节|部分|章|节|部|分)\s*[:：-]?\s*/i, '')
    .trim()
}

function extractFirstImageUrl(value: string): string {
  const markdownMatch = value.match(/!\[[^\]]*]\(([^)\s]+)(?:\s+['"][^'"]*['"])?\)/)
  if (markdownMatch) return markdownMatch[1].trim()

  const htmlMatch = value.match(/<img\b[^>]*\bsrc=['"]([^'"]+)['"][^>]*>/i)
  return htmlMatch?.[1]?.trim() || ''
}

function stripImages(value: string): string {
  return value
    .replace(/!\[[^\]]*]\(([^)\s]+)(?:\s+['"][^'"]*['"])?\)/g, '')
    .replace(/<img\b[^>]*\bsrc=['"]([^'"]+)['"][^>]*>/gi, '')
    .trim()
}

function timelineSectionsHaveUsableTime(sections: TimelineSection[]): boolean {
  return sections.some(section => section.endTime > section.startTime)
}

function normalizeTranscriptSegments(segments: Segment[]): Segment[] {
  return [...segments]
    .filter(segment => {
      return (
        Number.isFinite(segment.start) &&
        Number.isFinite(segment.end) &&
        segment.end >= segment.start &&
        segment.text?.trim()
      )
    })
    .sort((a, b) => a.start - b.start)
}

function extractUntimedTimelineSectionsFromMarkdown(markdown: string): TimelineSection[] {
  const sections: TimelineSection[] = []
  const headingRe = /^#{3,6}\s+(.+?)\s*$/
  let current: TimelineSection | null = null

  const pushCurrent = () => {
    if (!current) return
    current.content = stripImages(current.content)
    if (current.title || current.content) sections.push(current)
    current = null
  }

  for (const rawLine of markdown.split(/\r\n|\r|\n/)) {
    const line = rawLine.trim()
    const headingMatch = line.match(headingRe)
    if (headingMatch) {
      pushCurrent()
      current = {
        key: `markdown-untimed-${sections.length}`,
        title: cleanSectionTitle(headingMatch[1]) || `片段 ${sections.length + 1}`,
        content: '',
        startTime: 0,
        endTime: 0,
        screenshotUrl: '',
      }
      continue
    }

    if (current && line && !line.startsWith('#')) {
      current.content += `${rawLine.trim()}\n`
    }
  }

  pushCurrent()
  return sections
}

function alignTimelineSectionsToSegments(
  hints: TimelineSection[],
  segments: Segment[]
): TimelineSection[] {
  const normalizedSegments = normalizeTranscriptSegments(segments)
  if (normalizedSegments.length === 0) return []

  const desiredCount = hints.length || Math.ceil(normalizedSegments.length / 8)
  const groupCount = Math.min(normalizedSegments.length, Math.max(1, desiredCount))

  return Array.from({ length: groupCount }, (_, index) => {
    const startIndex = Math.floor((index * normalizedSegments.length) / groupCount)
    const endIndex = Math.max(
      startIndex,
      Math.floor(((index + 1) * normalizedSegments.length) / groupCount) - 1
    )
    const group = normalizedSegments.slice(startIndex, endIndex + 1)
    const first = group[0]
    const last = group[group.length - 1]
    const hint = hints[index]
    const text = group.map(segment => segment.text.trim()).join(' ')
    const title =
      hint?.title?.trim() || text.slice(0, 28) || `片段 ${index + 1}`

    return {
      key: hint?.key || `transcript-${index}`,
      title,
      content: stripImages(hint?.content || text),
      startTime: first.start,
      endTime: Math.max(last.end, first.start),
      screenshotUrl: hint?.screenshotUrl || '',
    }
  })
}

export function extractTimelineSectionsFromMarkdown(markdown: string): TimelineSection[] {
  const sections: TimelineSection[] = []
  const headingRe =
    /^#{2,6}\s+(.+?)[（(［[]\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*(?:-|~|–|—|至|到)\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*[）)］\]]\s*$/
  const bulletRe =
    /^[-*]\s+\[\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*(?:-|~|–|—|至|到)\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*\]\s*(?:(?:\*\*)?([^*:：]+)(?:\*\*)?\s*[:：-])?\s*(.*)$/
  let current: TimelineSection | null = null

  const pushCurrent = () => {
    if (!current) return
    const screenshotUrl = extractFirstImageUrl(current.content)
    sections.push({
      ...current,
      title: current.title || `片段 ${sections.length + 1}`,
      content: stripImages(current.content),
      screenshotUrl: current.screenshotUrl || screenshotUrl,
    })
    current = null
  }

  for (const rawLine of markdown.split(/\r\n|\r|\n/)) {
    const line = rawLine.trim()
    const headingMatch = line.match(headingRe)
    if (headingMatch) {
      pushCurrent()
      const startTime = parseTimestamp(headingMatch[2]) || 0
      const endTime = parseTimestamp(headingMatch[3]) || startTime
      current = {
        key: `markdown-${sections.length}`,
        title: cleanSectionTitle(headingMatch[1]) || `片段 ${sections.length + 1}`,
        content: '',
        startTime,
        endTime,
        screenshotUrl: '',
      }
      continue
    }

    const bulletMatch = line.match(bulletRe)
    if (bulletMatch) {
      pushCurrent()
      const startTime = parseTimestamp(bulletMatch[1]) || 0
      const endTime = parseTimestamp(bulletMatch[2]) || startTime
      sections.push({
        key: `markdown-${sections.length}`,
        title: cleanSectionTitle(bulletMatch[3] || '') || `片段 ${sections.length + 1}`,
        content: stripImages(bulletMatch[4] || ''),
        startTime,
        endTime,
        screenshotUrl: extractFirstImageUrl(bulletMatch[4] || ''),
      })
      continue
    }

    if (current && line && !line.startsWith('#')) {
      current.content += `${rawLine.trim()}\n`
    }
  }

  pushCurrent()
  return sections.filter(section => section.endTime >= section.startTime)
}

export function getTaskTimelineSections(task: Task, markdown = ''): TimelineSection[] {
  const chapters = task.audioMeta?.chapters || []
  const normalized = chapters
    .map((chapter, index) => {
      const startTime = coerceTimestamp(chapter.start_time)
      const endTime = coerceTimestamp(chapter.end_time)
      return {
        key: `chapter-${chapter.chunk_index ?? index}`,
        title: chapter.title?.trim() || `片段 ${index + 1}`,
        content: stripImages(chapter.content || ''),
        startTime,
        endTime: endTime >= startTime ? endTime : startTime,
        screenshotUrl: chapter.screenshot_url || chapter.image_url || chapter.thumbnail_url || '',
      }
    })
    .filter(
      section => section.startTime > 0 || section.endTime > 0 || section.title || section.content
    )

  if (normalized.length > 0) {
    if (timelineSectionsHaveUsableTime(normalized)) return normalized
    const alignedSections = alignTimelineSectionsToSegments(normalized, task.transcript?.segments || [])
    return alignedSections.length > 0 ? alignedSections : normalized
  }

  const timedMarkdownSections = extractTimelineSectionsFromMarkdown(markdown)
  if (timedMarkdownSections.length > 0 && timelineSectionsHaveUsableTime(timedMarkdownSections)) {
    return timedMarkdownSections
  }

  const untimedMarkdownSections = extractUntimedTimelineSectionsFromMarkdown(markdown)
  const transcriptAlignedSections = alignTimelineSectionsToSegments(
    untimedMarkdownSections,
    task.transcript?.segments || []
  )
  if (transcriptAlignedSections.length > 0) return transcriptAlignedSections

  return timedMarkdownSections.length > 0 ? timedMarkdownSections : untimedMarkdownSections
}

export function parseBackendDate(value: string | undefined): Date | null {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed || trimmed === 'builtin') return null

  const hasTimezone = /(?:z|[+-]\d{2}:?\d{2})$/i.test(trimmed)
  let normalized = trimmed.replace(' ', 'T')
  if (!hasTimezone && /^\d{4}-\d{2}-\d{2}T/.test(normalized)) {
    normalized += 'Z'
  }
  normalized = normalized.replace(/(\.\d{3})\d+(Z|[+-]\d{2}:?\d{2})$/i, '$1$2')

  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDate(value: string | undefined): string {
  const date = parseBackendDate(value)
  if (!date) return ''

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
