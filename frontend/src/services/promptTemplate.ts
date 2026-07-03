import { createLocalId, readLocalValue, writeLocalValue } from '@/services/fallback'

export interface PromptTemplate {
  id: string
  name: string
  content: string
  createdAt: string
  updatedAt: string
  isBuiltIn?: boolean
}

export interface PromptDraft {
  name: string
  content: string
  templateId: string | null
}

const PROMPT_TEMPLATE_STORAGE_KEY = 'ai-video-prompt-templates'
const PROMPT_DRAFT_STORAGE_KEY = 'ai-video-prompt-draft'

export const builtinPromptTemplates: PromptTemplate[] = [
  {
    id: 'builtin-course-notes',
    name: '课程笔记',
    content: `请把内容整理成结构化课程笔记：
1. 先总结 3-5 条核心结论
2. 按章节整理重点，补充关键概念和案例
3. 对重要术语做简短解释
4. 最后输出一段便于复习的总结`,
    createdAt: 'builtin',
    updatedAt: 'builtin',
    isBuiltIn: true,
  },
  {
    id: 'builtin-highlight-quotes',
    name: '提取金句',
    content: `请提炼最值得记录的关键表达：
1. 提取 5-10 条高价值观点
2. 每条附一句简短说明，解释它为什么重要
3. 保留原意，去掉口语赘述
4. 最后补一段适合收藏转发的总结`,
    createdAt: 'builtin',
    updatedAt: 'builtin',
    isBuiltIn: true,
  },
  {
    id: 'builtin-chapter-summary',
    name: '章节总结',
    content: `请按内容脉络输出章节总结：
1. 自动划分主要章节并命名
2. 每章用 2-4 句话概括核心内容
3. 标出章节之间的承接关系
4. 最后补一段整段内容的总览`,
    createdAt: 'builtin',
    updatedAt: 'builtin',
    isBuiltIn: true,
  },
  {
    id: 'builtin-action-items',
    name: '行动清单',
    content: `请把内容整理成可执行的行动清单：
1. 提取明确的步骤、方法和待办事项
2. 区分立即执行、后续跟进、准备资源
3. 重点写清楚执行顺序和注意事项
4. 最后补一段风险提醒`,
    createdAt: 'builtin',
    updatedAt: 'builtin',
    isBuiltIn: true,
  },
]

function normalizePromptTemplate(value: unknown): PromptTemplate | null {
  if (!value || typeof value !== 'object') return null

  const item = value as Partial<PromptTemplate>
  const id = typeof item.id === 'string' ? item.id.trim() : ''
  const name = typeof item.name === 'string' ? item.name.trim() : ''
  const content = typeof item.content === 'string' ? item.content.trim() : ''

  if (!id || !name || !content) return null

  return {
    id,
    name,
    content,
    createdAt: typeof item.createdAt === 'string' ? item.createdAt : new Date().toISOString(),
    updatedAt: typeof item.updatedAt === 'string' ? item.updatedAt : new Date().toISOString(),
    isBuiltIn: false,
  }
}

export function listSavedPromptTemplates(): PromptTemplate[] {
  const saved = readLocalValue<unknown[]>(PROMPT_TEMPLATE_STORAGE_KEY, [])
  return saved
    .map(normalizePromptTemplate)
    .filter((template): template is PromptTemplate => Boolean(template))
    .sort((left, right) => right.updatedAt.localeCompare(left.updatedAt))
}

export function savePromptTemplate(input: {
  id?: string
  name: string
  content: string
}): PromptTemplate {
  const now = new Date().toISOString()
  const name = input.name.trim()
  const content = input.content.trim()
  const templates = listSavedPromptTemplates()
  const targetId = input.id?.trim() || ''
  const templateId = targetId || createLocalId('prompt_template')
  const existingTemplate = templates.find(template => template.id === templateId)

  const nextTemplate: PromptTemplate = {
    id: templateId,
    name,
    content,
    createdAt: existingTemplate?.createdAt || now,
    updatedAt: now,
  }

  const nextTemplates = templates.filter(template => template.id !== templateId)
  nextTemplates.unshift(nextTemplate)
  writeLocalValue(PROMPT_TEMPLATE_STORAGE_KEY, nextTemplates)
  return nextTemplate
}

export function removePromptTemplate(id: string): void {
  const nextTemplates = listSavedPromptTemplates().filter(template => template.id !== id)
  writeLocalValue(PROMPT_TEMPLATE_STORAGE_KEY, nextTemplates)
}

export function readPromptDraft(): PromptDraft {
  const draft = readLocalValue<Partial<PromptDraft>>(PROMPT_DRAFT_STORAGE_KEY, {})
  return {
    name: typeof draft.name === 'string' ? draft.name : '',
    content: typeof draft.content === 'string' ? draft.content : '',
    templateId: typeof draft.templateId === 'string' ? draft.templateId : null,
  }
}

export function writePromptDraft(draft: PromptDraft): void {
  writeLocalValue(PROMPT_DRAFT_STORAGE_KEY, {
    name: draft.name,
    content: draft.content,
    templateId: draft.templateId,
  })
}

export function clearPromptDraft(): void {
  writeLocalValue(PROMPT_DRAFT_STORAGE_KEY, {
    name: '',
    content: '',
    templateId: null,
  })
}
