import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronDown,
  ExternalLink,
  Link2,
  Loader2,
  Search,
  Sparkles,
  Upload,
  X,
} from 'lucide-react'
import toast from 'react-hot-toast'
import { generateNote } from '@/services/note'
import { uploadFile } from '@/services/upload'
import { useModelStore } from '@/store/modelStore'
import { useTaskStore } from '@/store/taskStore'
import { noteStyles } from '@/constant/note'

interface GenerateViewProps {
  backendReady?: boolean
  onSubmitted: () => void
  onOpenSettings: () => void
}

function ModelSelectionModal({
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
    <div className="fixed right-8 top-20 z-50 w-[min(28rem,calc(100vw-2rem))]">
      <div className="flex max-h-[calc(100vh-7rem)] w-full flex-col rounded-xl border border-neutral-800 bg-[#111111] shadow-2xl">
        <div className="flex items-center justify-between border-b border-neutral-800/50 px-6 py-4">
          <h2 className="text-lg font-bold text-neutral-200">选择模型</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-neutral-500 transition-colors hover:text-neutral-300"
            aria-label="关闭"
          >
            <X size={18} />
          </button>
        </div>

        <div className="border-b border-neutral-800/50 p-4">
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
  const { addPendingTask, setCurrentTask } = useTaskStore()
  const { modelList, loading: modelLoading, loadEnabledModels } = useModelStore()
  const [singleUrl, setSingleUrl] = useState('')
  const [batchUrls, setBatchUrls] = useState('')
  const [prompt, setPrompt] = useState('')
  const [promptName, setPromptName] = useState('')
  const [selectedModel, setSelectedModel] = useState('')
  const [selectedStyle, setSelectedStyle] = useState('minimal')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [activeTab, setActiveTab] = useState<'link' | 'batch' | 'upload'>('link')
  const [showModelModal, setShowModelModal] = useState(false)
  const [showLinkDropdown, setShowLinkDropdown] = useState(false)
  const linkDropdownRef = useRef<HTMLDivElement>(null)

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

  const selectedModelItem = useMemo(
    () => modelList.find(model => model.model_name === selectedModel),
    [modelList, selectedModel]
  )

  const submitUrl = async (url: string, platform = 'bilibili') => {
    const targetUrl = url.trim()
    if (!targetUrl) {
      toast.error('请输入视频链接')
      return
    }

    if (!selectedModelItem) {
      toast.error('请先配置并选择一个可用模型')
      onOpenSettings()
      return
    }

    setIsSubmitting(true)
    try {
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
      setCurrentTask(data.task_id)
      setSingleUrl('')
      setBatchUrls('')
      onSubmitted()
    } catch (error) {
      console.error('提交任务失败:', error)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSubmit = async () => {
    if (activeTab === 'batch') {
      const urls = batchUrls
        .split(/[\n,，]+/)
        .map(item => item.trim())
        .filter(Boolean)

      if (urls.length === 0) {
        toast.error('请输入至少一个视频链接')
        return
      }

      await submitUrl(urls[0])
      if (urls.length > 1) {
        toast('Demo 阶段先提交第一条链接，其余链接稍后接入批量队列。')
      }
      return
    }

    await submitUrl(singleUrl)
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
      toast.error('上传失败，请重试')
    } finally {
      setIsUploading(false)
    }
  }

  const selectedStyleLabel =
    noteStyles.find(style => style.value === selectedStyle)?.label || selectedStyle

  return (
    <div className="custom-scrollbar flex flex-1 flex-col overflow-y-auto bg-[#0E0E0E] p-10 text-neutral-200">
      <div className="mx-auto w-full max-w-[1200px]">
        <h1 className="mb-8 text-2xl font-bold">看得更少，学得更多：加速音视频学习</h1>

        <div className="flex gap-10">
          <div className="flex flex-1 flex-col">
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

            {activeTab === 'link' && (
              <div>
                <label className="mb-2 block text-sm font-medium text-neutral-400">
                  输入 Bilibili 视频链接
                </label>
                <input
                  type="text"
                  value={singleUrl}
                  onChange={event => setSingleUrl(event.target.value)}
                  placeholder="https://www.bilibili.com/video/..."
                  className="w-full rounded-xl border border-neutral-800 bg-[#141414] px-4 py-3 text-sm text-neutral-200 transition-colors placeholder:text-neutral-600 focus:border-neutral-600 focus:outline-none"
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
                          <Sparkles size={18} />
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
                    '提交第一条链接'
                  )}
                </button>
              </div>
            )}

            {activeTab === 'upload' && (
              <div
                className="flex h-[400px] flex-col items-center justify-center rounded-xl border border-dashed border-neutral-800 bg-[#141414] text-neutral-500"
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

          <div className="flex w-[420px] shrink-0 flex-col gap-8">
            <div>
              <div className="grid grid-cols-2 gap-x-6 gap-y-6">
                <div className="space-y-6">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      onClick={() => setShowModelModal(true)}
                      className="flex max-w-[180px] items-center gap-1.5 rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 py-1.5 text-xs font-medium text-neutral-200 transition-colors hover:border-neutral-700"
                    >
                      {modelLoading ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : (
                        <Sparkles size={14} />
                      )}
                      <span className="truncate">{selectedModel || '选择模型'}</span>
                    </button>
                    <span className="text-xs text-neutral-400">大语言模型</span>
                  </div>

                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      className="flex items-center gap-1.5 rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 py-1.5 text-xs font-medium text-neutral-200"
                    >
                      简体中文
                      <ChevronDown size={14} />
                    </button>
                    <span className="text-xs text-neutral-400">输出语言</span>
                  </div>
                </div>

                <div className="space-y-6">
                  <div className="flex items-center gap-3">
                    <button
                      type="button"
                      className="flex items-center gap-1.5 rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 py-1.5 text-xs font-medium text-neutral-200"
                    >
                      自动识别
                      <ChevronDown size={14} />
                    </button>
                    <span className="text-xs text-neutral-400">音频语言</span>
                  </div>

                  <div className="flex items-center gap-3">
                    <select
                      value={selectedStyle}
                      onChange={event => setSelectedStyle(event.target.value)}
                      className="max-w-[150px] rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 py-1.5 text-xs font-medium text-neutral-200 outline-none"
                    >
                      {noteStyles.map(style => (
                        <option key={style.value} value={style.value}>
                          {style.label}
                        </option>
                      ))}
                    </select>
                    <span className="text-xs text-neutral-400">{selectedStyleLabel}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="h-px w-full bg-neutral-800/50" />

            <div>
              <div className="mb-4 flex items-center justify-between">
                <h3 className="text-sm font-bold text-neutral-300">提示词内容</h3>
                <button
                  type="button"
                  onClick={() => toast('提示词模板管理稍后接入本地持久化。')}
                  className="text-xs text-primary transition-colors hover:text-primary/80"
                >
                  保存为模板
                </button>
              </div>
              <textarea
                value={prompt}
                onChange={event => setPrompt(event.target.value)}
                placeholder="可选：补充你希望总结关注的重点，例如提取论点、案例、代码步骤..."
                className="mb-4 min-h-[160px] w-full resize-none rounded-xl border border-neutral-800 bg-[#141414] p-3 text-xs text-neutral-300 transition-colors placeholder:text-neutral-600 focus:border-neutral-600 focus:outline-none"
              />

              <div className="mb-4">
                <h3 className="mb-2 text-sm font-bold text-neutral-300">取个名字</h3>
                <input
                  type="text"
                  value={promptName}
                  onChange={event => setPromptName(event.target.value)}
                  placeholder="提示词标题"
                  className="w-full rounded-xl border border-neutral-800 bg-[#141414] px-4 py-2 text-sm text-neutral-200 transition-colors placeholder:text-neutral-600 focus:border-neutral-600 focus:outline-none"
                />
              </div>

              <div className="flex flex-col gap-4">
                <div className="flex flex-wrap items-center gap-3 text-xs text-neutral-400">
                  <span className="flex items-center gap-1">
                    <ExternalLink size={12} />
                    Prompt:
                  </span>
                  {['课程笔记', '提取金句', '章节总结', '行动清单'].map(item => (
                    <button
                      key={item}
                      type="button"
                      onClick={() =>
                        setPrompt(current => `${current}${current ? '\n' : ''}${item}`)
                      }
                      className="transition-colors hover:text-neutral-200"
                    >
                      {item}
                    </button>
                  ))}
                </div>

                <div className="mt-2 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => {
                      setPrompt('')
                      setPromptName('')
                    }}
                    className="rounded-lg border border-neutral-800 px-4 py-1.5 text-sm font-medium text-neutral-400 transition-colors hover:border-neutral-600 hover:text-neutral-200"
                  >
                    清除
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      toast(
                        promptName
                          ? `已保留当前提示词：${promptName}`
                          : '当前提示词会随本次任务提交'
                      )
                    }
                    className="rounded-lg border border-neutral-700 bg-neutral-800 px-4 py-1.5 text-sm font-medium text-neutral-200 transition-colors hover:bg-neutral-700"
                  >
                    保存
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
      {showModelModal && (
        <ModelSelectionModal
          selectedModel={selectedModel}
          backendReady={backendReady}
          onSelect={setSelectedModel}
          onClose={() => setShowModelModal(false)}
        />
      )}
    </div>
  )
}
