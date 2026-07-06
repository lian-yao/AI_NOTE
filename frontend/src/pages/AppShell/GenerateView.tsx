import { useEffect, useMemo, useRef, useState, type ClipboardEvent } from 'react'
import {
  ChevronDown,
  ExternalLink,
  Link2,
  Loader2,
  Search,
  SlidersHorizontal,
  Sparkles,
  Upload,
  WandSparkles,
  X,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { generateNote } from '@/services/note'
import {
  builtinPromptTemplates,
  clearPromptDraft,
  listSavedPromptTemplates,
  readPromptDraft,
  removePromptTemplate,
  savePromptTemplate,
  writePromptDraft,
  type PromptTemplate,
} from '@/services/promptTemplate'
import { uploadFile } from '@/services/upload'
import {
  getNoteRaw,
  listVideos,
  parseVideo,
  type ParseVideoResponse,
  type VideoItem,
} from '@/services/video'
import { useModelStore } from '@/store/modelStore'
import { isMockBackend, isMockLikeTask, type Task, useTaskStore } from '@/store/taskStore'
import { noteStyles } from '@/constant/note'

interface GenerateViewProps {
  backendReady?: boolean
  onSubmitted: () => void
  onOpenSettings: () => void
}

function audioMetaFromParsed(
  parsed: ParseVideoResponse,
  platform: string,
  targetUrl: string,
  fallbackVideoId?: string,
) {
  return {
    cover_url: parsed.cover_url || '',
    duration: parsed.duration_seconds || 0,
    file_path: '',
    platform,
    raw_info: {
      uploader: parsed.uploader || '',
      uploader_uid: parsed.uploader_uid || '',
      bvid: parsed.bvid || '',
      avid: parsed.avid || null,
      description: parsed.description || '',
      source_url: parsed.source_url || targetUrl,
      player_url: parsed.player_url || '',
      embed_url: parsed.embed_url || '',
      upload_date: parsed.upload_date || '',
      view_count: parsed.view_count || null,
      like_count: parsed.like_count || null,
      comment_count: parsed.comment_count || null,
      tags: parsed.tags || [],
      chapters: parsed.chapters || [],
    },
    title: parsed.title || targetUrl,
    video_id: fallbackVideoId || parsed.video_id || '',
    source_url: parsed.source_url || targetUrl,
    player_url: parsed.player_url || null,
    embed_url: parsed.embed_url || null,
    chapters: parsed.chapters || [],
  }
}

function extractBvid(value: string): string {
  return value.match(/BV[0-9A-Za-z]+/)?.[0] || ''
}

const VIDEO_URL_PATTERN =
  /(?:https?:\/\/|www\.|b23\.tv\/|(?:[\w-]+\.)?bilibili\.com\/)[^\s<>"'`|\\\u3000-\u303f\uff00-\uff65]+/gi
const BILIBILI_ID_PATTERN = /\b(?:BV[0-9A-Za-z]{10}|av\d+)\b/gi

function normalizeVideoUrlCandidate(candidate: string): string | null {
  const trimmed = candidate
    .trim()
    .replace(/^[<>"'`([{]+/, '')
    .replace(/[<>"'`)\]}.,;:!]+$/g, '')

  if (!trimmed) return null

  const withProtocol = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`

  try {
    const url = new URL(withProtocol)
    const host = url.hostname.toLowerCase()
    const supportedHost =
      host === 'b23.tv' || host === 'bilibili.com' || host.endsWith('.bilibili.com')

    return supportedHost ? url.href : null
  } catch {
    return null
  }
}

function extractVideoIdentity(value: string): string {
  const bvid = value.match(/BV[0-9A-Za-z]{10}/i)?.[0]
  if (bvid) return bvid.toUpperCase()

  const avid = value.match(/\bav(\d+)\b/i)?.[1]
  return avid ? `av${avid}` : ''
}

function videoUrlDedupeKey(value: string): string {
  const identity = extractVideoIdentity(value)
  if (!identity) return value.toLowerCase()

  try {
    const url = new URL(value)
    const page = url.searchParams.get('p') || '1'
    return `${identity}:p=${page}`
  } catch {
    return identity
  }
}

function extractVideoUrls(value: string): string[] {
  const urlCandidates = value.match(VIDEO_URL_PATTERN) || []
  const idCandidates = Array.from(value.matchAll(BILIBILI_ID_PATTERN), match =>
    `https://www.bilibili.com/video/${match[0]}`,
  )
  const seen = new Set<string>()

  return [...urlCandidates, ...idCandidates].reduce<string[]>((urls, candidate) => {
    const normalizedUrl = normalizeVideoUrlCandidate(candidate)
    if (!normalizedUrl) return urls

    const dedupeKey = videoUrlDedupeKey(normalizedUrl)
    if (seen.has(dedupeKey)) return urls

    seen.add(dedupeKey)
    urls.push(normalizedUrl)
    return urls
  }, [])
}

function rawInfoBvid(rawInfo: unknown): string {
  if (!rawInfo || typeof rawInfo !== 'object') return ''
  const item = rawInfo as {
    bvid?: unknown
    backend_video?: { bvid?: unknown }
  }
  return String(item.bvid || item.backend_video?.bvid || '')
}

function normalizeVideoStatus(status: string): Task['status'] {
  const value = status.toLowerCase()
  if (value === 'completed' || value === 'success') return 'SUCCESS'
  if (value === 'failed') return 'FAILED'
  if (value === 'pending') return 'PENDING'
  if (value === 'downloading') return 'DOWNLOADING'
  if (value === 'transcribing') return 'TRANSCRIBING'
  if (value === 'generating') return 'SUMMARIZING'
  if (value === 'storing') return 'SAVING'
  return 'RUNNING'
}

function taskMatchesVideo(task: Task, data: {
  parsed?: ParseVideoResponse | null
  targetUrl: string
  targetBvid: string
}) {
  if (task.status === 'FAILED') return false

  const parsedVideoId = data.parsed?.video_id || ''
  const taskVideoId = task.audioMeta?.video_id || task.id
  if (parsedVideoId && (taskVideoId === parsedVideoId || task.id === parsedVideoId)) return true

  if (!data.targetBvid) return false
  return (
    rawInfoBvid(task.audioMeta?.raw_info) === data.targetBvid ||
    extractBvid(task.formData?.video_url || '') === data.targetBvid ||
    extractBvid(task.audioMeta?.source_url || '') === data.targetBvid
  )
}

function backendVideoMatches(video: VideoItem, data: {
  parsed?: ParseVideoResponse | null
  targetUrl: string
  targetBvid: string
}) {
  if (video.status?.toLowerCase() === 'failed') return false
  if (data.parsed?.video_id && video.video_id === data.parsed.video_id) return true
  if (!data.targetBvid) return false
  return video.bvid === data.targetBvid || extractBvid(video.url || '') === data.targetBvid
}

function backendVideoToTask(video: VideoItem, markdown: string): Task {
  return {
    id: video.video_id,
    status: normalizeVideoStatus(video.status),
    markdown:
      markdown ||
      `# ${video.title || '后端视频笔记'}\n\n后端已返回视频记录，笔记原文暂未返回。`,
    transcript: {
      full_text: '',
      language: 'zh-CN',
      raw: null,
      segments: [],
    },
    audioMeta: {
      cover_url: video.cover_url || '',
      duration: video.duration_seconds || 0,
      file_path: video.audio_path || '',
      platform: 'bilibili',
      raw_info: {
        uploader: video.uploader || '',
        bvid: video.bvid || '',
        backend_video: video,
      },
      title: video.title || video.url,
      video_id: video.video_id,
      source_url: video.source_url || video.url,
      player_url: video.player_url || null,
      embed_url: video.embed_url || null,
      chapters: video.chapters || [],
    },
    createdAt: video.created_at || new Date().toISOString(),
    formData: {
      video_url: video.url,
      link: true,
      screenshot: false,
      platform: 'bilibili',
      quality: '1080p',
      model_name: isMockBackend ? 'mock-backend' : 'backend',
      provider_id: isMockBackend ? 'mock-backend' : 'backend',
      format: ['summary'],
      style: 'minimal',
    },
  }
}

function ModelSelectionDropdown({
  selectedModel,
  backendReady = true,
  onSelect,
  onClose,
}: {
  selectedModel: string
  backendReady?: boolean
  onSelect: (modelName: string) => void
  onClose: () => void
}) {
  const { modelList, loading, loadEnabledModels } = useModelStore()
  const [search, setSearch] = useState('')

  useEffect(() => {
    loadEnabledModels({ silent: true })
  }, [backendReady, loadEnabledModels])

  const filteredModels = modelList.filter(model =>
    model.model_name.toLowerCase().includes(search.trim().toLowerCase())
  )

  const groupedModels = filteredModels.reduce<Record<string, typeof modelList>>((acc, model) => {
    const key = model.provider_id || 'default'
    acc[key] = [...(acc[key] || []), model]
    return acc
  }, {})

  return (
    <div className="absolute top-[calc(100%+0.5rem)] left-0 z-50 w-full sm:min-w-[20rem]">
      <div className="flex max-h-[min(24rem,calc(100vh-14rem))] w-full origin-top flex-col rounded-xl border border-neutral-800 bg-[#111111] shadow-2xl shadow-black/40 ring-1 ring-white/5">
        <div className="flex items-center justify-between border-b border-neutral-800/50 px-4 py-3">
          <h2 className="text-sm font-bold text-neutral-200">选择模型</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-neutral-500 transition-colors hover:text-neutral-300"
            aria-label="关闭"
          >
            <X size={18} />
          </button>
        </div>

        <div className="border-b border-neutral-800/50 p-3">
          <div className="relative">
            <Search
              size={16}
              className="absolute top-1/2 left-3 -translate-y-1/2 text-neutral-500"
            />
            <input
              type="text"
              value={search}
              onChange={event => setSearch(event.target.value)}
              placeholder="搜索已启用模型..."
              className="w-full rounded-xl border border-neutral-800 bg-[#1A1A1A] py-2 pr-4 pl-9 text-sm text-neutral-200 transition-colors focus:border-neutral-600 focus:outline-none"
            />
          </div>
        </div>

        <div className="custom-scrollbar flex-1 overflow-y-auto p-2">
          {!backendReady && !loading && filteredModels.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-neutral-500">
              后端未就绪，模型列表暂未加载。
            </div>
          )}

          {loading && (
            <div className="flex items-center justify-center gap-2 py-8 text-sm text-neutral-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在加载模型...
            </div>
          )}

          {backendReady && !loading && filteredModels.length === 0 && (
            <div className="px-4 py-8 text-center text-sm text-neutral-500">
              暂无可用模型，请先在设置中配置 Provider 和启用模型。
            </div>
          )}

          {Object.entries(groupedModels).map(([providerId, models]) => (
            <div key={providerId} className="px-4 py-3">
              <div className="mb-2 text-xs font-medium text-neutral-500">
                Provider {providerId.slice(0, 8)}
              </div>
              <div className="space-y-1">
                {models.map(model => (
                  <button
                    type="button"
                    key={`${model.provider_id}-${model.model_name}`}
                    onClick={() => {
                      onSelect(model.model_name)
                      onClose()
                    }}
                    className={`group flex w-full items-center justify-between rounded-lg p-2 text-left transition-colors hover:bg-[#1A1A1A] ${
                      selectedModel === model.model_name ? 'bg-primary/10' : ''
                    }`}
                  >
                    <span className="flex min-w-0 items-center gap-2 text-sm text-neutral-200">
                      <Sparkles
                        size={14}
                        className={
                          selectedModel === model.model_name
                            ? 'shrink-0 text-primary'
                            : 'shrink-0 text-neutral-500 group-hover:text-neutral-300'
                        }
                      />
                      <span className="truncate">{model.model_name}</span>
                    </span>
                    {selectedModel === model.model_name && (
                      <span className="text-xs text-primary">已选</span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default function GenerateView({
  backendReady = true,
  onSubmitted,
  onOpenSettings,
}: GenerateViewProps) {
  const { addPendingTask, setCurrentTask, tasks: storedTasks, updateTaskContent, upsertTask } = useTaskStore()
  const { modelList, loading: modelLoading, loadEnabledModels } = useModelStore()
  const [singleUrl, setSingleUrl] = useState('')
  const [batchUrls, setBatchUrls] = useState('')
  const [prompt, setPrompt] = useState('')
  const [promptName, setPromptName] = useState('')
  const [activePromptTemplateId, setActivePromptTemplateId] = useState<string | null>(null)
  const [savedPromptTemplates, setSavedPromptTemplates] = useState<PromptTemplate[]>(() =>
    listSavedPromptTemplates(),
  )
  const [selectedModel, setSelectedModel] = useState('')
  const [selectedStyle, setSelectedStyle] = useState('minimal')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [activeTab, setActiveTab] = useState<'link' | 'batch' | 'upload'>('link')
  const [showModelModal, setShowModelModal] = useState(false)
  const [showLinkDropdown, setShowLinkDropdown] = useState(false)
  const [showAdvancedConfig, setShowAdvancedConfig] = useState(false)
  const linkDropdownRef = useRef<HTMLDivElement>(null)
  const modelDropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!backendReady) return
    loadEnabledModels({ silent: true })
  }, [backendReady, loadEnabledModels])

  useEffect(() => {
    if (!selectedModel && modelList[0]) {
      setSelectedModel(modelList[0].model_name)
    }
  }, [modelList, selectedModel])

  useEffect(() => {
    if (!showLinkDropdown) return

    const handlePointerDown = (event: PointerEvent) => {
      if (linkDropdownRef.current?.contains(event.target as Node)) return
      setShowLinkDropdown(false)
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowLinkDropdown(false)
      }
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [showLinkDropdown])

  useEffect(() => {
    if (!showModelModal) return

    const handlePointerDown = (event: PointerEvent) => {
      if (modelDropdownRef.current?.contains(event.target as Node)) return
      setShowModelModal(false)
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setShowModelModal(false)
      }
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)

    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [showModelModal])

  useEffect(() => {
    if (!showAdvancedConfig) {
      setShowModelModal(false)
    }
  }, [showAdvancedConfig])

  useEffect(() => {
    const draft = readPromptDraft()
    setPrompt(draft.content)
    setPromptName(draft.name)
    setActivePromptTemplateId(draft.templateId)
  }, [])

  useEffect(() => {
    writePromptDraft({
      name: promptName,
      content: prompt,
      templateId: activePromptTemplateId,
    })
  }, [activePromptTemplateId, prompt, promptName])

  const selectedModelItem = useMemo(
    () => modelList.find(model => model.model_name === selectedModel),
    [modelList, selectedModel]
  )
  const tasks = useMemo(
    () => (isMockBackend ? storedTasks : storedTasks.filter(task => !isMockLikeTask(task))),
    [storedTasks],
  )

  const submitUrl = async (url: string, platform = 'bilibili') => {
    const targetUrl = platform === 'bilibili' ? extractVideoUrls(url)[0] || '' : url.trim()
    if (!targetUrl) {
      toast.error('请输入有效的 Bilibili 视频链接')
      return
    }

    setIsSubmitting(true)
    try {
      const parsed =
        platform === 'bilibili'
          ? await parseVideo(targetUrl, { silent: true }).catch(() => null)
          : null
      const targetBvid = parsed?.bvid || extractBvid(targetUrl)
      const duplicateData = { parsed, targetUrl, targetBvid }
      let existingTask =
        platform === 'bilibili'
          ? tasks.find(task => taskMatchesVideo(task, duplicateData))
          : undefined

      if (!existingTask && platform === 'bilibili' && (parsed?.video_id || targetBvid)) {
        const backendVideos = await listVideos({ page: 1, page_size: 100 }, { silent: true })
          .then(res => res.items)
          .catch(() => [])
        const existingVideo = backendVideos.find(video => backendVideoMatches(video, duplicateData))
        if (existingVideo) {
          const markdown =
            existingVideo.status === 'completed'
              ? await getNoteRaw(existingVideo.video_id, { silent: true }).catch(() => '')
              : ''
          existingTask = backendVideoToTask(existingVideo, markdown)
          upsertTask(existingTask)
        }
      }

      if (existingTask) {
        const shouldRegenerate = window.confirm(
          `视频「${existingTask.audioMeta?.title || targetUrl}」已经生成过笔记，是否重新生成？\n\n确定：重新生成\n取消：打开已有笔记`,
        )
        if (!shouldRegenerate) {
          setCurrentTask(existingTask.id)
          toast.success('已打开已有笔记')
          onSubmitted()
          return
        }
      }

      if (!selectedModelItem) {
        toast.error('请先配置并选择一个可用模型')
        onOpenSettings()
        return
      }

      const payload = {
        video_url: targetUrl,
        platform,
        quality: '1080p' as const,
        link: true,
        screenshot: false,
        model_name: selectedModelItem.model_name,
        provider_id: selectedModelItem.provider_id,
        format: ['toc', 'link', 'summary'],
        style: selectedStyle,
        extras: prompt.trim() ? prompt.trim() : undefined,
        video_understanding: false,
        video_interval: 6,
        grid_size: [2, 2],
      }
      const data = await generateNote(payload)
      addPendingTask(data.task_id, platform, payload)
      if (parsed) {
        updateTaskContent(data.task_id, {
          audioMeta: audioMetaFromParsed(parsed, platform, targetUrl, data.video_id),
        })
      }
      if (data.result) {
        updateTaskContent(data.task_id, {
          status: 'SUCCESS',
          markdown: data.result.markdown,
          transcript: data.result.transcript,
          audioMeta: parsed
            ? {
              ...data.result.audio_meta,
              ...audioMetaFromParsed(parsed, platform, targetUrl, data.video_id),
            }
            : data.result.audio_meta,
        })
      }
      setCurrentTask(data.task_id)
      setSingleUrl('')
      setBatchUrls('')
      onSubmitted()
    } catch (error) {
      const apiError = error as {
        message?: string
        response?: {
          data?: {
            error?: { message?: string }
            message?: string
          }
        }
      }
      const msg = apiError.response?.data?.error?.message
        || apiError.response?.data?.message
        || apiError.message
        || '提交任务失败，请检查网络连接和后端数据库是否正常'
      toast.error(msg)
      console.error('提交任务失败:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSubmit = async () => {
    if (activeTab === 'batch') {
      const urls = extractVideoUrls(batchUrls)

      if (urls.length === 0) {
        toast.error('请输入至少一个有效的 Bilibili 视频链接')
        return
      }

      setBatchUrls(urls.join('\n'))
      await submitUrl(urls[0])
      if (urls.length > 1) {
        toast('Demo 阶段先提交第一条链接，其余链接稍后接入批量队列。')
      }
      return
    }

    const targetUrl = extractVideoUrls(singleUrl)[0] || ''
    if (targetUrl) setSingleUrl(targetUrl)
    await submitUrl(targetUrl || singleUrl)
  }

  const handleSingleUrlPaste = (event: ClipboardEvent<HTMLInputElement>) => {
    const targetUrl = extractVideoUrls(event.clipboardData.getData('text'))[0]
    if (!targetUrl) return

    event.preventDefault()
    setSingleUrl(targetUrl)
  }

  const handleBatchUrlsPaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const pastedUrls = extractVideoUrls(event.clipboardData.getData('text'))
    if (pastedUrls.length === 0) return

    event.preventDefault()
    setBatchUrls(extractVideoUrls(`${batchUrls}\n${pastedUrls.join('\n')}`).join('\n'))
  }

  const handleFileUpload = async (file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    setIsUploading(true)
    try {
      const data = await uploadFile(formData)
      await submitUrl(data.url, 'local')
    } catch (error) {
      console.error('上传失败:', error)
      toast.error(error instanceof Error ? error.message : '上传失败，请重试')
    } finally {
      setIsUploading(false)
    }
  }

  const selectedStyleLabel =
    noteStyles.find(style => style.value === selectedStyle)?.label || selectedStyle
  const allPromptTemplates = [...builtinPromptTemplates, ...savedPromptTemplates]
  const hasPromptContent = Boolean(prompt.trim() || promptName.trim())

  function applyPromptTemplate(template: PromptTemplate) {
    setPrompt(template.content)
    setPromptName(template.name)
    setActivePromptTemplateId(template.id)
    toast.success(`已加载模板：${template.name}`)
  }

  function handleSavePromptTemplate() {
    const normalizedName = promptName.trim()
    const normalizedPrompt = prompt.trim()

    if (!normalizedName) {
      toast.error('请先填写提示词标题')
      return
    }

    if (!normalizedPrompt) {
      toast.error('请先填写提示词内容')
      return
    }

    const matchedBuiltInTemplate = builtinPromptTemplates.find(
      template => template.id === activePromptTemplateId,
    )
    if (matchedBuiltInTemplate) {
      setActivePromptTemplateId(null)
    }

    const savedTemplate = savePromptTemplate({
      id:
        activePromptTemplateId &&
        !builtinPromptTemplates.some(template => template.id === activePromptTemplateId)
          ? activePromptTemplateId
          : undefined,
      name: normalizedName,
      content: normalizedPrompt,
    })

    const nextTemplates = listSavedPromptTemplates()
    setSavedPromptTemplates(nextTemplates)
    setActivePromptTemplateId(savedTemplate.id)
    toast.success(`模板已保存：${savedTemplate.name}`)
  }

  function handleDeletePromptTemplate(template: PromptTemplate) {
    if (template.isBuiltIn) {
      toast.error('内置模板暂不支持删除')
      return
    }

    const confirmed = window.confirm(`删除模板「${template.name}」？`)
    if (!confirmed) return

    removePromptTemplate(template.id)
    const nextTemplates = listSavedPromptTemplates()
    setSavedPromptTemplates(nextTemplates)

    if (activePromptTemplateId === template.id) {
      setActivePromptTemplateId(null)
    }

    toast.success(`已删除模板：${template.name}`)
  }

  return (
    <div className="custom-scrollbar flex flex-1 overflow-y-auto bg-[#0E0E0E] px-6 py-8 text-neutral-200 sm:px-10">
      <div className="mx-auto grid min-h-full w-full max-w-[760px] place-items-center py-8 sm:py-10">
        <div className="w-full transition-transform duration-500 ease-out">
        <div className="mb-6 flex w-fit rounded-xl border border-neutral-800 bg-[#161616] p-1">
          <div ref={linkDropdownRef} className="relative">
            <button
              type="button"
              onClick={() => {
                if (activeTab === 'upload') {
                  setActiveTab('link')
                }
                setShowLinkDropdown(value => !value)
              }}
              aria-expanded={showLinkDropdown}
              aria-haspopup="menu"
              className={`flex items-center gap-2 rounded-lg px-6 py-2 text-sm font-medium transition-colors ${
                activeTab === 'link' || activeTab === 'batch'
                  ? 'bg-[#222222] text-neutral-200'
                  : 'text-neutral-400 hover:bg-[#1A1A1A] hover:text-neutral-200'
              }`}
            >
              <Link2 size={16} />
              {activeTab === 'batch' ? '批量链接' : '链接'}
              <ChevronDown
                size={14}
                className={`opacity-50 transition-transform ${showLinkDropdown ? 'rotate-180' : ''}`}
              />
            </button>
            {showLinkDropdown && (
              <div
                role="menu"
                className="absolute top-full left-0 z-20 mt-1 w-32 overflow-hidden rounded-lg border border-neutral-800 bg-[#1A1A1A] shadow-xl"
              >
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setActiveTab('link')
                    setShowLinkDropdown(false)
                  }}
                  className="w-full px-4 py-2 text-left text-sm text-neutral-300 transition-colors hover:bg-neutral-800 hover:text-neutral-200"
                >
                  单链接
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    setActiveTab('batch')
                    setShowLinkDropdown(false)
                  }}
                  className="w-full px-4 py-2 text-left text-sm text-neutral-300 transition-colors hover:bg-neutral-800 hover:text-neutral-200"
                >
                  批量链接
                </button>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => {
              setActiveTab('upload')
              setShowLinkDropdown(false)
            }}
            className={`flex items-center gap-2 rounded-lg px-6 py-2 text-sm font-medium transition-colors ${
              activeTab === 'upload'
                ? 'bg-[#222222] text-neutral-200'
                : 'text-neutral-400 hover:bg-[#1A1A1A] hover:text-neutral-200'
            }`}
          >
            <Upload size={16} />
            上传
          </button>
        </div>

        <div className="w-full">
          {activeTab === 'link' && (
            <div>
              <label className="mb-2 block text-sm font-medium text-neutral-400">
                输入 Bilibili 视频链接
              </label>
              <input
                type="text"
                value={singleUrl}
                onChange={event => setSingleUrl(event.target.value)}
                onPaste={handleSingleUrlPaste}
                placeholder="https://www.bilibili.com/video/..."
                className="h-12 w-full rounded-xl border border-neutral-800 bg-[#141414] px-4 text-sm text-neutral-200 transition-colors placeholder:text-neutral-600 focus:border-neutral-600 focus:outline-none"
              />
              <button
                type="button"
                onClick={handleSubmit}
                disabled={isSubmitting || !singleUrl.trim()}
                className="mt-4 flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-[#E0E0E0] font-bold text-black transition-colors hover:bg-white disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSubmitting ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <>
                    <WandSparkles size={18} />
                    一键总结
                  </>
                )}
              </button>
            </div>
          )}

          {activeTab === 'batch' && (
            <div>
              <label className="mb-2 block text-sm font-medium text-neutral-400">
                批量总结
                <span className="ml-2 text-xs font-normal text-neutral-500">
                  Demo 阶段会先提交第一条链接
                </span>
              </label>
              <textarea
                value={batchUrls}
                onChange={event => setBatchUrls(event.target.value)}
                onPaste={handleBatchUrlsPaste}
                className="min-h-[160px] w-full resize-none rounded-xl border border-neutral-800 bg-[#141414] p-4 text-sm text-neutral-200 transition-colors placeholder:text-neutral-600 focus:border-neutral-600 focus:outline-none"
                placeholder="每行一个 Bilibili 视频链接"
              />
              <button
                type="button"
                onClick={handleSubmit}
                disabled={isSubmitting || !batchUrls.trim()}
                className="mt-4 flex h-12 w-full items-center justify-center gap-2 rounded-lg border border-neutral-700 bg-[#222222] font-bold text-neutral-200 transition-colors hover:bg-[#2A2A2A] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {isSubmitting ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <>
                    <WandSparkles size={18} />
                    提交第一条链接
                  </>
                )}
              </button>
            </div>
          )}

          {activeTab === 'upload' && (
            <div
              className="flex h-[320px] flex-col items-center justify-center rounded-xl border border-dashed border-neutral-800 bg-[#141414] text-neutral-500"
              onDragOver={event => {
                event.preventDefault()
                event.stopPropagation()
              }}
              onDrop={event => {
                event.preventDefault()
                const file = event.dataTransfer.files?.[0]
                if (file) handleFileUpload(file)
              }}
            >
              {isUploading || isSubmitting ? (
                <Loader2 className="mb-4 h-8 w-8 animate-spin text-neutral-400" />
              ) : (
                <Upload size={32} className="mb-4 opacity-50" />
              )}
              <p className="text-sm">支持上传本地音视频文件</p>
              <button
                type="button"
                disabled={isUploading || isSubmitting}
                onClick={() => {
                  const input = document.createElement('input')
                  input.type = 'file'
                  input.accept = 'video/*,audio/*'
                  input.onchange = event => {
                    const file = (event.target as HTMLInputElement).files?.[0]
                    if (file) handleFileUpload(file)
                  }
                  input.click()
                }}
                className="mt-4 rounded-lg bg-neutral-800 px-6 py-2 text-sm text-neutral-200 transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                选择文件
              </button>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={() => setShowAdvancedConfig(value => !value)}
          aria-expanded={showAdvancedConfig}
          className="mt-6 flex w-full items-center justify-between rounded-xl border border-neutral-800 bg-[#121212] px-4 py-3 text-left transition-all duration-300 hover:border-neutral-700 hover:bg-[#161616] active:scale-[0.995]"
        >
          <span className="flex min-w-0 items-center gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#1A1A1A] text-neutral-300">
              <SlidersHorizontal size={16} />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-bold text-neutral-200">具体配置</span>
              <span className="block truncate text-xs text-neutral-500">
                {selectedModel || '未选择模型'} · {selectedStyleLabel}
              </span>
            </span>
          </span>
          <span className="ml-4 flex shrink-0 items-center gap-2 text-xs font-medium text-neutral-400">
            {showAdvancedConfig ? '收起' : '显示'}
            <ChevronDown
              size={16}
              className={`transition-transform duration-300 ${showAdvancedConfig ? 'rotate-180' : ''}`}
            />
          </span>
        </button>

        <div
          aria-hidden={!showAdvancedConfig}
          className={`grid w-full transition-[grid-template-rows,opacity,margin,transform] duration-300 ease-out ${
            showAdvancedConfig
              ? 'mt-3 grid-rows-[1fr] translate-y-0 opacity-100'
              : 'mt-0 grid-rows-[0fr] -translate-y-2 opacity-0'
          }`}
        >
          <div className={`min-h-0 ${showAdvancedConfig ? 'overflow-visible' : 'overflow-hidden'}`}>
            <div
              className={`w-full rounded-xl border border-neutral-800 bg-[#111111] p-5 shadow-2xl shadow-black/20 transition-[transform,opacity] duration-300 ease-out ${
                showAdvancedConfig
                  ? 'translate-y-0 opacity-100'
                  : 'pointer-events-none -translate-y-2 opacity-0'
              }`}
            >
            <div className="grid gap-4 sm:grid-cols-2">
              <div ref={modelDropdownRef} className="relative">
                <label className="mb-2 block text-xs font-medium text-neutral-500">
                  大语言模型
                </label>
                <button
                  type="button"
                  onClick={() => setShowModelModal(value => !value)}
                  aria-expanded={showModelModal}
                  aria-haspopup="listbox"
                  className="flex h-10 w-full items-center gap-2 rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 text-sm font-medium text-neutral-200 transition-colors hover:border-neutral-700"
                >
                  {modelLoading ? (
                    <Loader2 size={14} className="shrink-0 animate-spin" />
                  ) : (
                    <Sparkles size={14} className="shrink-0" />
                  )}
                  <span className="min-w-0 flex-1 truncate text-left">{selectedModel || '选择模型'}</span>
                  <ChevronDown
                    size={14}
                    className={`shrink-0 text-neutral-500 transition-transform duration-300 ${
                      showModelModal ? 'rotate-180' : ''
                    }`}
                  />
                </button>
                {showModelModal && (
                  <ModelSelectionDropdown
                    selectedModel={selectedModel}
                    backendReady={backendReady}
                    onSelect={setSelectedModel}
                    onClose={() => setShowModelModal(false)}
                  />
                )}
              </div>

              <div>
                <label className="mb-2 block text-xs font-medium text-neutral-500">
                  笔记风格
                </label>
                <select
                  value={selectedStyle}
                  onChange={event => setSelectedStyle(event.target.value)}
                  className="h-10 w-full rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 text-sm font-medium text-neutral-200 outline-none transition-colors hover:border-neutral-700 focus:border-neutral-600"
                >
                  {noteStyles.map(style => (
                    <option key={style.value} value={style.value}>
                      {style.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="my-5 h-px w-full bg-neutral-800/50" />

            <div>
              <div className="mb-4 flex items-center justify-between gap-4">
                <h3 className="text-sm font-bold text-neutral-300">提示词内容</h3>
                <button
                  type="button"
                  onClick={handleSavePromptTemplate}
                  className="shrink-0 text-xs text-primary transition-colors hover:text-primary/80"
                >
                  保存为模板
                </button>
              </div>
              <textarea
                value={prompt}
                onChange={event => setPrompt(event.target.value)}
                placeholder="可选：补充你希望总结关注的重点，例如提取论点、案例、代码步骤..."
                className="mb-4 min-h-[150px] w-full resize-none rounded-xl border border-neutral-800 bg-[#141414] p-3 text-xs text-neutral-300 transition-colors placeholder:text-neutral-600 focus:border-neutral-600 focus:outline-none"
              />

              <div className="mb-4">
                <h3 className="mb-2 text-sm font-bold text-neutral-300">取个名字</h3>
                <input
                  type="text"
                  value={promptName}
                  onChange={event => setPromptName(event.target.value)}
                  placeholder="提示词标题"
                  className="h-10 w-full rounded-xl border border-neutral-800 bg-[#141414] px-4 text-sm text-neutral-200 transition-colors placeholder:text-neutral-600 focus:border-neutral-600 focus:outline-none"
                />
              </div>

              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center gap-3 text-xs text-neutral-400">
                  <span className="flex items-center gap-1">
                    <ExternalLink size={12} />
                    Prompt:
                  </span>
                  {allPromptTemplates.map(template => (
                    <div
                      key={template.id}
                      className={`group inline-flex items-center gap-1 rounded-md border px-2 py-1 transition-colors ${
                        activePromptTemplateId === template.id
                          ? 'border-neutral-600 bg-neutral-800 text-neutral-100'
                          : 'border-transparent text-neutral-400 hover:border-neutral-800 hover:bg-neutral-900 hover:text-neutral-200'
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => applyPromptTemplate(template)}
                        className="transition-colors"
                      >
                        {template.name}
                      </button>
                      {!template.isBuiltIn && (
                        <button
                          type="button"
                          onClick={() => handleDeletePromptTemplate(template)}
                          className="text-neutral-500 transition-colors hover:text-red-300"
                          aria-label={`删除模板 ${template.name}`}
                        >
                          <X size={12} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>

                <div className="rounded-xl border border-neutral-800 bg-[#121212] px-3 py-2 text-xs text-neutral-500">
                  {activePromptTemplateId
                    ? `当前模板：${
                      allPromptTemplates.find(template => template.id === activePromptTemplateId)?.name ||
                      '未命名模板'
                    }，当前编辑会自动保存到本地草稿`
                    : '当前内容会自动保存到本地草稿，可直接编辑后保存为模板'}
                </div>

                {hasPromptContent && (
                  <div className="mt-2 flex items-center justify-end">
                    <button
                      type="button"
                      onClick={() => {
                        setPrompt('')
                        setPromptName('')
                        setActivePromptTemplateId(null)
                        clearPromptDraft()
                      }}
                      className="rounded-lg border border-neutral-800 px-4 py-1.5 text-sm font-medium text-neutral-400 transition-colors hover:border-neutral-600 hover:text-neutral-200"
                    >
                      清除
                    </button>
                  </div>
                )}
              </div>
            </div>
            </div>
          </div>
        </div>
        </div>
      </div>
    </div>
  )
}
