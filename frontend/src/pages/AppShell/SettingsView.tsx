import { useEffect, useMemo, useState, type ComponentType, type ReactNode } from 'react'
import {
  Activity,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Database,
  Download,
  Eye,
  EyeOff,
  FileText as FileTextIcon,
  FolderSearch,
  HardDrive,
  Key,
  Loader2,
  Power,
  Plus,
  QrCode,
  RefreshCcw,
  Save,
  Search,
  Server,
  Settings2,
  Trash2,
  Video as VideoIcon,
  X,
} from 'lucide-react'
import { QRCode as AntQRCode } from 'antd'
import toast from 'react-hot-toast'
import type { IProvider } from '@/types'
import { useSystemStore, type CacheDirectoryKey, type StoragePathConfig } from '@/store/configStore'
import { useProviderStore } from '@/store/providerStore'
import {
  addModel,
  addProvider,
  deleteModelById,
  deleteProviderById,
  fetchModels,
  fetchProviderModelRowsById,
  testConnection,
  updateProviderById,
} from '@/services/model'
import {
  getDownloaderCookie,
  pollBilibiliQrCodeLogin,
  startBilibiliQrCodeLogin,
  updateDownloaderCookie,
  validateDownloaderCookie,
  type BilibiliQrCodePollResult,
  type BilibiliQrCodeSession,
  type DownloaderCookieValidation,
} from '@/services/downloader'
import { getProxyConfig, updateProxyConfig, type ProxyConfig } from '@/services/proxy'
import {
  downloadModel,
  getModelsStatus,
  getTranscriberConfig,
  updateTranscriberConfig,
  getDownloadProgress,
  type ModelStatus,
  type TranscriberConfig,
} from '@/services/transcriber'
import { getDeployStatus, getSystemStats, type DeployStatus, type SystemStats } from '@/services/system'
import { isSkippedApiResult } from '@/services/fallback'
import { IconSwitch } from './components/IconSwitch'
import BackendInitDialog from '@/components/BackendInitDialog'

type ProviderDraft = Omit<IProvider, 'id'> & { id?: string }
type SettingsSectionId = 'provider' | 'platform' | 'transcriber' | 'storage' | 'monitor'

const SETTINGS_SECTIONS: {
  id: SettingsSectionId
  label: string
  detail: string
  icon: ComponentType<{ size?: number; className?: string }>
}[] = [
  { id: 'provider', label: '模型接入', detail: 'Provider / API Key / Models', icon: Key },
  { id: 'platform', label: '平台数据', detail: 'Bilibili Cookie / Proxy', icon: Database },
  { id: 'transcriber', label: '本地转写', detail: 'Whisper / Transcriber', icon: HardDrive },
  { id: 'storage', label: '存储管理', detail: 'Data / Cache', icon: HardDrive },
  { id: 'monitor', label: '运行状态', detail: 'Backend / FFmpeg / CUDA', icon: Activity },
]

const PROVIDER_PRESETS = [
  {
    value: 'openai-compatible',
    label: 'OpenAI 兼容',
    description: '默认推荐，适用于 OpenAI、代理网关和大多数兼容端点。',
    match: ['openai'],
    name: 'OpenAI',
    logo: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
  },
  {
    value: 'deepseek',
    label: 'DeepSeek',
    description: 'DeepSeek 官方 OpenAI 兼容接口。',
    match: ['deepseek'],
    name: 'DeepSeek',
    logo: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com',
  },
  {
    value: 'qwen',
    label: 'Qwen',
    description: '阿里云 DashScope OpenAI 兼容模式。',
    match: ['qwen'],
    name: 'Qwen',
    logo: 'Qwen',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
  },
  {
    value: 'gemini',
    label: 'Gemini',
    description: 'Gemini OpenAI 兼容接口。',
    match: ['gemini'],
    name: 'Gemini',
    logo: 'Gemini',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai/',
  },
  {
    value: 'groq',
    label: 'Groq',
    description: 'Groq OpenAI 兼容接口。',
    match: ['groq'],
    name: 'Groq',
    logo: 'Groq',
    baseUrl: 'https://api.groq.com/openai/v1',
  },
  {
    value: 'ollama',
    label: 'Ollama',
    description: '本地 Ollama OpenAI 兼容接口。',
    match: ['ollama'],
    name: 'Ollama',
    logo: 'Ollama',
    baseUrl: 'http://127.0.0.1:11434/v1',
  },
  {
    value: 'custom',
    label: '自定义端点',
    description: '自托管模型网关或其它 OpenAI 兼容服务。',
    match: ['custom'],
    name: 'Custom Provider',
    logo: 'custom',
    baseUrl: '',
  },
]

interface SettingsViewProps {
  backendReady?: boolean
  backendFailed?: boolean
  backendLastError?: string | null
  onBackendRetry?: () => void
}

const defaultProviderPreset = PROVIDER_PRESETS[0]

function getProviderPreset(value: string) {
  return PROVIDER_PRESETS.find(item => item.value === value) || defaultProviderPreset
}

function makeUniqueProviderName(providers: IProvider[], preset = defaultProviderPreset) {
  const names = new Set(providers.map(provider => provider.name.trim().toLowerCase()))
  const baseName = preset.value === 'custom' ? 'Custom Provider' : `${preset.name} API`
  let name = baseName
  let index = 2

  while (names.has(name.toLowerCase())) {
    name = `${baseName} ${index}`
    index += 1
  }

  return name
}

function providerDraftFromPreset(
  preset = defaultProviderPreset,
  providers: IProvider[] = [],
): ProviderDraft {
  return {
    name: makeUniqueProviderName(providers, preset),
    logo: preset.logo,
    type: 'custom',
    apiKey: '',
    baseUrl: preset.baseUrl,
    enabled: 1,
  }
}

const CACHE_DIRECTORY_META: {
  key: CacheDirectoryKey
  label: string
  detail: string
  childDir: string
  storageKeys: string[]
}[] = [
  {
    key: 'downloads',
    label: '下载缓存',
    detail: '视频、音频下载过程中的中间文件',
    childDir: 'downloads',
    storageKeys: ['aivideo-cache-downloads'],
  },
  {
    key: 'transcripts',
    label: '转写缓存',
    detail: '字幕、分段文本与转写过程缓存',
    childDir: 'transcripts',
    storageKeys: ['aivideo-cache-transcripts'],
  },
  {
    key: 'covers',
    label: '封面缓存',
    detail: '视频封面与预览图缓存',
    childDir: 'covers',
    storageKeys: ['aivideo-cache-covers'],
  },
  {
    key: 'temp',
    label: '临时缓存',
    detail: '任务运行时的临时状态与短期缓存',
    childDir: 'temp',
    storageKeys: ['aivideo-cache-temp', 'aivideo-cache-runtime'],
  },
]

function joinConfiguredPath(rootPath: string, childDir: string) {
  const root = rootPath.trim().replace(/[\\/]+$/, '')
  if (!root) return childDir
  const separator = root.includes('\\') && !root.includes('/') ? '\\' : '/'
  return `${root}${separator}${childDir}`
}

function buildCacheDirectories(rootPath: string): Record<CacheDirectoryKey, string> {
  return CACHE_DIRECTORY_META.reduce(
    (directories, item) => ({
      ...directories,
      [item.key]: joinConfiguredPath(rootPath, item.childDir),
    }),
    {} as Record<CacheDirectoryKey, string>,
  )
}

function normalizeStoragePathConfig(
  config: Partial<StoragePathConfig> & { knowledgeBasePath?: string },
): StoragePathConfig {
  const fallback = {
    dataRootPath: './data',
    cacheRootPath: './data/cache',
    cacheDirectories: buildCacheDirectories('./data/cache'),
    lastCacheClearedAt: null,
  }
  const cacheDirectories = config.cacheDirectories || fallback.cacheDirectories

  return {
    ...fallback,
    ...config,
    dataRootPath: (config.dataRootPath || config.knowledgeBasePath || fallback.dataRootPath).trim(),
    cacheRootPath: (config.cacheRootPath || fallback.cacheRootPath).trim(),
    cacheDirectories: CACHE_DIRECTORY_META.reduce(
      (directories, item) => ({
        ...directories,
        [item.key]: cacheDirectories[item.key]?.trim() || '',
      }),
      {} as Record<CacheDirectoryKey, string>,
    ),
  }
}

function getLocalStorageBytes(keys: string[]) {
  if (typeof localStorage === 'undefined') return 0
  return keys.reduce((total, key) => {
    const value = localStorage.getItem(key)
    if (value === null) return total
    return total + new TextEncoder().encode(`${key}${value}`).length
  }, 0)
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function formatCacheClearedAt(value: string | null) {
  if (!value) return '从未清理'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function isTauriRuntime() {
  return typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
}

export default function SettingsView({
  backendReady = true,
  backendFailed = false,
  backendLastError = null,
  onBackendRetry,
}: SettingsViewProps) {
  const [activeSection, setActiveSection] = useState<SettingsSectionId>('provider')
  const activeMeta =
    SETTINGS_SECTIONS.find(section => section.id === activeSection) || SETTINGS_SECTIONS[0]
  const ActiveSectionIcon = activeMeta.icon

  return (
    <div className="custom-scrollbar flex-1 overflow-y-auto bg-[#0E0E0E] text-neutral-200">
      <div className="mx-auto max-w-6xl px-8 py-10">
        <div className="mb-8 flex flex-col gap-2">
          <h1 className="text-2xl font-bold">设置</h1>
          <p className="text-sm text-neutral-500">按工作流拆分配置，避免模型、本地环境和平台数据混在一起。</p>
        </div>

        <div className="grid gap-6 lg:grid-cols-[240px_minmax(0,1fr)]">
          <nav className="h-fit rounded-xl border border-neutral-800 bg-[#141414] p-2">
            {SETTINGS_SECTIONS.map(section => {
              const Icon = section.icon
              const active = activeSection === section.id

              return (
                <button
                  key={section.id}
                  type="button"
                  onClick={() => setActiveSection(section.id)}
                  className={`flex w-full items-center gap-3 rounded-lg px-3 py-3 text-left transition-colors ${
                    active
                      ? 'bg-neutral-800 text-neutral-100'
                      : 'text-neutral-400 hover:bg-[#1A1A1A] hover:text-neutral-200'
                  }`}
                >
                  <Icon size={17} className={active ? 'text-primary' : 'text-neutral-500'} />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium">{section.label}</span>
                    <span className="mt-0.5 block truncate text-[11px] text-neutral-500">
                      {section.detail}
                    </span>
                  </span>
                </button>
              )
            })}
          </nav>

          <div className="min-w-0">
            <div className="mb-4 flex items-center gap-2 text-neutral-400">
              <ActiveSectionIcon size={18} />
              <h2 className="text-sm font-bold">{activeMeta.label}</h2>
            </div>
            {!backendReady && !backendFailed && (
              <div className="mb-4 rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-xs text-amber-100">
                后端正在后台启动，配置界面已先渲染；依赖后端的数据稍后可刷新加载。
              </div>
            )}
            <BackendInitDialog
              open={false}
              failed={backendFailed}
              lastError={backendLastError}
              onRetry={onBackendRetry}
              placement="inline"
            />
            {activeSection === 'provider' && <ProviderSection />}
            {activeSection === 'platform' && <DownloaderSection />}
            {activeSection === 'transcriber' && <TranscriberSection />}
            {activeSection === 'storage' && <StorageSection />}
            {activeSection === 'monitor' && <MonitorSection />}
          </div>
        </div>
      </div>
    </div>
  )
}

function ProviderSection() {
  const providers = useProviderStore(state => state.provider)
  const fetchProviderList = useProviderStore(state => state.fetchProviderList)
  const [providersLoaded, setProvidersLoaded] = useState(false)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [drafts, setDrafts] = useState<Record<string, ProviderDraft>>({})
  const [showApiKeys, setShowApiKeys] = useState<Record<string, boolean>>({})
  const [savingProviderId, setSavingProviderId] = useState<string | null>(null)
  const [testingProviderId, setTestingProviderId] = useState<string | null>(null)
  const [deletingProviderId, setDeletingProviderId] = useState<string | null>(null)
  const [modelLoadingByProvider, setModelLoadingByProvider] = useState<Record<string, boolean>>({})
  const [remoteModelsByProvider, setRemoteModelsByProvider] = useState<Record<string, RemoteModel[]>>({})
  const [enabledModelsByProvider, setEnabledModelsByProvider] = useState<Record<string, SavedModel[]>>({})
  const [togglingModelKey, setTogglingModelKey] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [createPreset, setCreatePreset] = useState(defaultProviderPreset.value)
  const [createDraft, setCreateDraft] = useState<ProviderDraft>(() =>
    providerDraftFromPreset(defaultProviderPreset),
  )
  const [createShowApiKey, setCreateShowApiKey] = useState(false)
  const [creating, setCreating] = useState(false)
  const [providersLoadFailed, setProvidersLoadFailed] = useState(false)

  useEffect(() => {
    let mounted = true

    fetchProviderList({ silent: true })
      .then(ok => {
        if (mounted) setProvidersLoadFailed(!ok)
      })
      .finally(() => {
        if (mounted) setProvidersLoaded(true)
      })

    return () => {
      mounted = false
    }
  }, [fetchProviderList])

  useEffect(() => {
    setDrafts(current => {
      const next: Record<string, ProviderDraft> = {}
      providers.forEach(provider => {
        next[provider.id] = current[provider.id] || provider
      })
      return next
    })

    setExpanded(current => {
      const next: Record<string, boolean> = {}
      providers.forEach(provider => {
        next[provider.id] = current[provider.id] ?? false
      })
      return next
    })
  }, [providers])

  useEffect(() => {
    providers.forEach(provider => {
      refreshEnabledModels(provider.id)
    })
  }, [providers])

  const updateProviderDraft = (providerId: string, field: keyof ProviderDraft, value: string | number) => {
    setDrafts(prev => ({
      ...prev,
      [providerId]: {
        ...prev[providerId],
        [field]: value,
      },
    }))
  }

  const updateCreateDraft = (field: keyof ProviderDraft, value: string | number) => {
    setCreateDraft(prev => ({ ...prev, [field]: value }))
  }

  const handleCreatePresetChange = (value: string) => {
    const preset = getProviderPreset(value)
    setCreatePreset(value)
    setCreateDraft(providerDraftFromPreset(preset, providers))
  }

  const handleCreateProvider = async () => {
    if (!createDraft.name.trim()) {
      toast.error('请填写 Provider 名称')
      return
    }
    if (!createDraft.baseUrl.trim()) {
      toast.error('请填写 Base URL')
      return
    }

    setCreating(true)
    try {
      const createdId = await addProvider({
        name: createDraft.name.trim(),
        api_key: createDraft.apiKey.trim(),
        base_url: createDraft.baseUrl.trim(),
        logo: createDraft.logo,
        type: 'custom',
      })
      await fetchProviderList()
      if (typeof createdId === 'string') {
        setExpanded(prev => ({ ...prev, [createdId]: true }))
      }
      setShowAddForm(false)
      setCreateDraft(providerDraftFromPreset(getProviderPreset(createPreset), providers))
      toast.success('Provider 已添加')
    } catch {
      // 拦截器已提示
    } finally {
      setCreating(false)
    }
  }

  const handleSaveProvider = async (providerId: string) => {
    const draft = drafts[providerId]
    if (!draft?.name.trim()) {
      toast.error('请填写 Provider 名称')
      return
    }
    if (!draft.baseUrl.trim()) {
      toast.error('请填写 Base URL')
      return
    }

    const apiKey = draft.apiKey.trim()
    const updatePayload = {
      id: providerId,
      name: draft.name.trim(),
      base_url: draft.baseUrl.trim(),
      logo: draft.logo,
      type: draft.type || 'custom',
      enabled: draft.enabled,
      ...(apiKey || !draft.has_api_key ? { api_key: apiKey } : {}),
    }

    setSavingProviderId(providerId)
    try {
      await updateProviderById(updatePayload)
      await fetchProviderList()
      toast.success('Provider 配置已保存')
    } catch {
      // 拦截器已提示
    } finally {
      setSavingProviderId(null)
    }
  }

  const handleToggleProviderEnabled = async (provider: IProvider) => {
    const nextEnabled = provider.enabled ? 0 : 1
    setSavingProviderId(provider.id)
    try {
      await updateProviderById({
        id: provider.id,
        name: provider.name,
        base_url: provider.baseUrl,
        enabled: nextEnabled,
      })
      await fetchProviderList()
      toast.success(nextEnabled ? 'Provider 已启用' : 'Provider 已禁用')
    } catch {
      // 拦截器已提示
    } finally {
      setSavingProviderId(null)
    }
  }

  const handleDeleteProvider = async (provider: IProvider) => {
    const ok = window.confirm(`删除 Provider「${provider.name}」？该 Provider 下已启用的模型也会一起移除。`)
    if (!ok) return

    setDeletingProviderId(provider.id)
    try {
      await deleteProviderById(provider.id)
      await fetchProviderList()
      setRemoteModelsByProvider(prev => {
        const next = { ...prev }
        delete next[provider.id]
        return next
      })
      setEnabledModelsByProvider(prev => {
        const next = { ...prev }
        delete next[provider.id]
        return next
      })
      toast.success('Provider 已删除')
    } catch {
      // 拦截器已提示
    } finally {
      setDeletingProviderId(null)
    }
  }

  const refreshEnabledModels = async (providerId: string) => {
    try {
      const models = await fetchProviderModelRowsById(providerId, { silent: true })
      setEnabledModelsByProvider(prev => ({
        ...prev,
        [providerId]: Array.isArray(models) ? models.map(model => ({
          id: model.id,
          model_name: model.model_name,
          enabled: model.enabled !== false,
        })) : [],
      }))
    } catch {
      setEnabledModelsByProvider(prev => ({ ...prev, [providerId]: [] }))
    }
  }

  const handleFetchRemoteModels = async (providerId: string) => {
    setModelLoadingByProvider(prev => ({ ...prev, [providerId]: true }))
    try {
      const response = await fetchModels(providerId)
      const models = normalizeRemoteModels(response)
      setRemoteModelsByProvider(prev => ({ ...prev, [providerId]: models }))
      await refreshEnabledModels(providerId)
      toast.success(models.length > 0 ? `已获取 ${models.length} 个模型` : '后端远程模型接口暂未实现，已显示本地启用模型')
    } catch {
      // 拦截器已提示
    } finally {
      setModelLoadingByProvider(prev => ({ ...prev, [providerId]: false }))
    }
  }

  const handleToggleModel = async (providerId: string, modelName: string) => {
    const enabledModel = enabledModelsByProvider[providerId]?.find(
      model => model.model_name === modelName && model.enabled !== false,
    )
    const toggleKey = `${providerId}:${modelName}`
    setTogglingModelKey(toggleKey)
    try {
      if (enabledModel) {
        await deleteModelById(Number(enabledModel.id))
      } else {
        await addModel({ provider_id: providerId, model_name: modelName })
      }
      await refreshEnabledModels(providerId)
    } catch {
      // 拦截器已提示
    } finally {
      setTogglingModelKey(null)
    }
  }

  const handleTestProvider = async (providerId: string) => {
    const firstModel = enabledModelsByProvider[providerId]?.find(
      model => model.enabled !== false,
    )?.model_name
    if (!firstModel) {
      toast.error('请先启用至少一个聊天模型')
      return
    }

    setTestingProviderId(providerId)
    try {
      const result = await testConnection({ id: providerId, model: firstModel })
      toast.success(isSkippedApiResult(result) ? '后端连通性测试接口暂未实现，已跳过' : '连通性测试成功')
    } catch {
      // 拦截器已提示
    } finally {
      setTestingProviderId(null)
    }
  }

  const handleAddFormToggle = () => {
    setShowAddForm(value => {
      const next = !value
      if (next) {
        const preset = getProviderPreset(createPreset)
        setCreateDraft(providerDraftFromPreset(preset, providers))
      }
      return next
    })
  }

  const refreshProviders = async () => {
    setProvidersLoaded(false)
    const ok = await fetchProviderList({ silent: true })
    setProvidersLoadFailed(!ok)
    setProvidersLoaded(true)
  }

  const providerCountLabel = !providersLoaded
    ? '正在加载提供商'
    : providersLoadFailed
      ? 'Provider 配置暂未加载'
      : `已添加 ${providers.length} 个提供商`

  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-lg font-semibold text-neutral-100">提供商</div>
          <div className="mt-1 text-sm text-neutral-500">{providerCountLabel}</div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={refreshProviders}
            className="flex items-center gap-1.5 rounded-lg border border-neutral-800 px-3 py-2 text-sm text-neutral-400 transition-colors hover:bg-neutral-800 hover:text-neutral-200"
          >
            <RefreshCcw size={15} />
            刷新
          </button>
          <button
            type="button"
            onClick={handleAddFormToggle}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-primary/80"
          >
            {showAddForm ? <X size={15} /> : <Plus size={15} />}
            {showAddForm ? '取消添加' : '添加提供商'}
          </button>
        </div>
      </div>

      {providersLoadFailed && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-xs text-amber-100">
          后端 Provider 配置暂未加载；仍可先编辑新增表单，后端恢复后刷新同步。
        </div>
      )}

      {showAddForm && (
        <ProviderEditPanel
          draft={createDraft}
          preset={createPreset}
          showApiKey={createShowApiKey}
          saving={creating}
          saveLabel="添加提供商"
          onPresetChange={handleCreatePresetChange}
          onToggleApiKey={() => setCreateShowApiKey(value => !value)}
          onChange={updateCreateDraft}
          onSave={handleCreateProvider}
        />
      )}

      <div className="space-y-3">
        {providersLoaded && providers.length === 0 && !showAddForm && (
          <div className="rounded-xl border border-dashed border-neutral-800 bg-[#141414] px-6 py-10 text-center text-sm text-neutral-500">
            暂无 Provider 配置，添加一个 OpenAI 兼容端点后即可获取模型列表。
          </div>
        )}

        {providers.map(provider => {
          const draft = drafts[provider.id] || provider
          const isExpanded = expanded[provider.id] ?? false
          const enabledModels = enabledModelsByProvider[provider.id] || []
          const remoteModels = remoteModelsByProvider[provider.id] || []
          const mergedModels = mergeRemoteAndEnabledModels(remoteModels, enabledModels)
          const chatModels = mergedModels.filter(model => !isEmbeddingModel(model.id))
          const embeddingModels = mergedModels.filter(model => isEmbeddingModel(model.id))
          const loadingModels = modelLoadingByProvider[provider.id] === true
          const enabledCount = enabledModels.filter(model => model.enabled !== false).length

          return (
            <div
              key={provider.id}
              className="overflow-hidden rounded-xl border border-neutral-800/90 bg-[#141414] shadow-[0_1px_0_rgba(255,255,255,0.03)]"
            >
              <div className="flex min-h-14 items-center gap-3 border-b border-neutral-800/80 px-4 py-2">
                <button
                  type="button"
                  onClick={() => setExpanded(prev => ({ ...prev, [provider.id]: !isExpanded }))}
                  className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-neutral-500 transition-colors hover:bg-neutral-800 hover:text-neutral-200"
                  aria-label={isExpanded ? '收起 Provider' : '展开 Provider'}
                >
                  {isExpanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                </button>
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="truncate text-base font-semibold text-neutral-100">{provider.name}</span>
                    {!provider.enabled && (
                      <span className="rounded-full border border-neutral-700 bg-neutral-800/80 px-2 py-0.5 text-[11px] text-neutral-400">
                        已禁用
                      </span>
                    )}
                  </div>
                  <div className="mt-0.5 truncate text-xs text-neutral-500">{provider.baseUrl}</div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <span className="hidden rounded-full border border-neutral-700/80 bg-neutral-800/90 px-3 py-1 text-xs text-neutral-300 md:inline-flex">
                    {enabledCount} 启用模型
                  </span>
                  <IconSwitch
                    checked={Boolean(provider.enabled)}
                    disabled={savingProviderId === provider.id}
                    label={provider.enabled ? '禁用 Provider' : '启用 Provider'}
                    onClick={() => handleToggleProviderEnabled(provider)}
                  />
                  <button
                    type="button"
                    onClick={() => setExpanded(prev => ({ ...prev, [provider.id]: true }))}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-neutral-500 transition-colors hover:bg-neutral-800 hover:text-neutral-200"
                    aria-label="编辑 Provider"
                  >
                    <Settings2 size={17} />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDeleteProvider(provider)}
                    disabled={deletingProviderId === provider.id}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-neutral-500 transition-colors hover:bg-red-500/10 hover:text-red-300 disabled:opacity-50"
                    aria-label="删除 Provider"
                  >
                    {deletingProviderId === provider.id ? (
                      <Loader2 size={17} className="animate-spin" />
                    ) : (
                      <Trash2 size={17} />
                    )}
                  </button>
                </div>
              </div>

              {isExpanded && (
                <div className="p-4">
                  <div className="mb-5 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_auto]">
                    <ProviderInlineFields
                      draft={draft}
                      showApiKey={showApiKeys[provider.id] === true}
                      onToggleApiKey={() =>
                        setShowApiKeys(prev => ({ ...prev, [provider.id]: !prev[provider.id] }))
                      }
                      onChange={(field, value) => updateProviderDraft(provider.id, field, value)}
                    />
                    <div className="flex flex-wrap items-end gap-2 xl:justify-end">
                      <button
                        type="button"
                        onClick={() => handleSaveProvider(provider.id)}
                        disabled={savingProviderId === provider.id}
                        className="flex h-9 items-center gap-1.5 rounded-lg bg-neutral-200 px-3 text-xs font-semibold text-neutral-950 transition-colors hover:bg-white disabled:opacity-50"
                      >
                        {savingProviderId === provider.id ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <Save size={14} />
                        )}
                        保存
                      </button>
                      <button
                        type="button"
                        onClick={() => handleTestProvider(provider.id)}
                        disabled={testingProviderId === provider.id || enabledCount === 0}
                        className="flex h-9 items-center gap-1.5 rounded-lg border border-neutral-700 bg-neutral-800 px-3 text-xs font-medium text-neutral-200 transition-colors hover:bg-neutral-700 disabled:opacity-50"
                      >
                        {testingProviderId === provider.id ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <Power size={14} />
                        )}
                        测试
                      </button>
                      <button
                        type="button"
                        onClick={() => handleFetchRemoteModels(provider.id)}
                        disabled={loadingModels}
                        className="flex h-9 items-center gap-1.5 rounded-lg border border-neutral-700 bg-neutral-800 px-3 text-xs font-medium text-neutral-200 transition-colors hover:bg-neutral-700 disabled:opacity-50"
                      >
                        {loadingModels ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <RefreshCcw size={14} />
                        )}
                        获取模型
                      </button>
                    </div>
                  </div>

                  <ModelTable
                    title="聊天模型"
                    models={chatModels}
                    enabledModels={enabledModels}
                    providerId={provider.id}
                    emptyText={remoteModels.length === 0 ? '点击“获取模型”从 Provider 拉取模型列表' : '暂无聊天模型'}
                    togglingModelKey={togglingModelKey}
                    onToggleModel={handleToggleModel}
                  />

                  <ModelTable
                    title="嵌入模型"
                    models={embeddingModels}
                    enabledModels={enabledModels}
                    providerId={provider.id}
                    emptyText={remoteModels.length === 0 ? '点击“获取模型”从 Provider 拉取模型列表' : '暂无嵌入模型'}
                    togglingModelKey={togglingModelKey}
                    onToggleModel={handleToggleModel}
                    showDimension
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

type SavedModel = { id: string | number; model_name: string; enabled?: boolean }
type RemoteModel = {
  id: string
  displayName: string
  dimension?: number | string
}

function getRemoteModelId(model: unknown): string {
  if (typeof model === 'string') return model
  if (!model || typeof model !== 'object') return ''

  const item = model as Record<string, unknown>
  const id = item.id || item.model || item.name || item.model_name
  return typeof id === 'string' ? id : ''
}

function normalizeRemoteModels(response: unknown): RemoteModel[] {
  const root = response as { models?: unknown; data?: unknown } | undefined
  const rawModels = Array.isArray(root?.models)
    ? root?.models
    : Array.isArray((root?.models as { data?: unknown[] } | undefined)?.data)
      ? (root?.models as { data?: unknown[] }).data
      : Array.isArray(root?.data)
        ? root?.data
        : Array.isArray(response)
          ? response
          : []
  const models = rawModels || []

  const map = new Map<string, RemoteModel>()
  models.forEach(rawModel => {
    const id = getRemoteModelId(rawModel)
    if (!id || map.has(id)) return

    const item = rawModel && typeof rawModel === 'object' ? (rawModel as Record<string, unknown>) : {}
    const dimension = item.dimension || item.dimensions || item.embedding_dimensions
    map.set(id, {
      id,
      displayName: typeof item.display_name === 'string' ? item.display_name : id,
      dimension: typeof dimension === 'number' || typeof dimension === 'string' ? dimension : undefined,
    })
  })

  return [...map.values()].sort((a, b) => a.id.localeCompare(b.id))
}

function mergeRemoteAndEnabledModels(remoteModels: RemoteModel[], enabledModels: SavedModel[]) {
  const map = new Map<string, RemoteModel>()
  remoteModels.forEach(model => map.set(model.id, model))
  enabledModels.forEach(model => {
    if (!map.has(model.model_name)) {
      map.set(model.model_name, {
        id: model.model_name,
        displayName: model.model_name,
      })
    }
  })
  return [...map.values()]
}

function isEmbeddingModel(modelName: string) {
  const lower = modelName.toLowerCase()
  return lower.includes('embed') || lower.includes('embedding') || lower.includes('bge')
}

function ProviderInlineFields({
  draft,
  showApiKey,
  onToggleApiKey,
  onChange,
}: {
  draft: ProviderDraft
  showApiKey: boolean
  onToggleApiKey: () => void
  onChange: (field: keyof ProviderDraft, value: string | number) => void
}) {
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
      <div>
        <label className="mb-1.5 block text-[11px] font-medium text-neutral-500">显示名称</label>
        <input
          type="text"
          value={draft.name}
          onChange={event => onChange('name', event.target.value)}
          className="w-full rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 py-2 text-sm text-neutral-200 outline-none focus:border-neutral-600"
        />
      </div>
      <div>
        <label className="mb-1.5 block text-[11px] font-medium text-neutral-500">Base URL</label>
        <input
          type="text"
          value={draft.baseUrl}
          onChange={event => onChange('baseUrl', event.target.value)}
          className="w-full rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 py-2 text-sm text-neutral-200 outline-none focus:border-neutral-600"
        />
      </div>
      <div>
        <label className="mb-1.5 block text-[11px] font-medium text-neutral-500">API Key</label>
        <div className="relative">
          <input
            type={showApiKey ? 'text' : 'password'}
            value={draft.apiKey}
            onChange={event => onChange('apiKey', event.target.value)}
            placeholder={draft.has_api_key ? '已配置，留空则不修改' : 'sk-...'}
            className="w-full rounded-lg border border-neutral-800 bg-[#1A1A1A] py-2 pl-3 pr-10 text-sm text-neutral-200 outline-none focus:border-neutral-600"
          />
          <button
            type="button"
            onClick={onToggleApiKey}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-neutral-500 transition-colors hover:text-neutral-300"
            aria-label={showApiKey ? '隐藏 API Key' : '显示 API Key'}
          >
            {showApiKey ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        </div>
      </div>
    </div>
  )
}

function ProviderEditPanel({
  draft,
  preset,
  showApiKey,
  saving,
  saveLabel,
  onPresetChange,
  onToggleApiKey,
  onChange,
  onSave,
}: {
  draft: ProviderDraft
  preset: string
  showApiKey: boolean
  saving: boolean
  saveLabel: string
  onPresetChange: (value: string) => void
  onToggleApiKey: () => void
  onChange: (field: keyof ProviderDraft, value: string | number) => void
  onSave: () => void
}) {
  const selectedPreset = getProviderPreset(preset)

  return (
    <div className="rounded-xl border border-neutral-800 bg-[#141414] p-4">
      <div className="mb-4 grid grid-cols-1 gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
        <div>
          <label className="mb-1.5 block text-[11px] font-medium text-neutral-500">Provider 预设</label>
          <select
            value={preset}
            onChange={event => onPresetChange(event.target.value)}
            className="w-full rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 py-2 text-sm text-neutral-200 outline-none focus:border-neutral-600"
          >
            {PROVIDER_PRESETS.map(item => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
          <div className="mt-2 text-xs leading-relaxed text-neutral-500">
            {selectedPreset.description}
          </div>
        </div>
        <ProviderInlineFields
          draft={draft}
          showApiKey={showApiKey}
          onToggleApiKey={onToggleApiKey}
          onChange={onChange}
        />
      </div>
      <button
        type="button"
        onClick={onSave}
        disabled={saving}
        className="flex h-9 items-center gap-1.5 rounded-lg bg-neutral-200 px-4 text-sm font-semibold text-neutral-950 transition-colors hover:bg-white disabled:opacity-50"
      >
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />}
        {saveLabel}
      </button>
    </div>
  )
}

function ModelTable({
  title,
  models,
  enabledModels,
  providerId,
  emptyText,
  togglingModelKey,
  onToggleModel,
  showDimension = false,
}: {
  title: string
  models: RemoteModel[]
  enabledModels: SavedModel[]
  providerId: string
  emptyText: string
  togglingModelKey: string | null
  onToggleModel: (providerId: string, modelName: string) => void
  showDimension?: boolean
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [searchText, setSearchText] = useState('')
  const enabledSet = new Set(
    enabledModels.filter(model => model.enabled !== false).map(model => model.model_name),
  )
  const normalizedSearchText = searchText.trim().toLowerCase()
  const filteredModels = useMemo(() => {
    if (!normalizedSearchText) return models

    return models.filter(model => {
      const fields = [
        model.id,
        model.displayName,
        model.dimension === undefined ? '' : String(model.dimension),
      ]
      return fields.some(field => field.toLowerCase().includes(normalizedSearchText))
    })
  }, [models, normalizedSearchText])
  const emptyResultText = searchText.trim() ? '没有匹配的模型' : emptyText

  return (
    <div className="mb-5 last:mb-0">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => setCollapsed(value => !value)}
          className="inline-flex min-w-0 items-center gap-2 rounded-lg px-1.5 py-1 text-left transition-colors hover:bg-neutral-800/80"
          aria-expanded={!collapsed}
        >
          {collapsed ? (
            <ChevronRight size={16} className="shrink-0 text-neutral-500" />
          ) : (
            <ChevronDown size={16} className="shrink-0 text-neutral-500" />
          )}
          <span className="truncate text-sm font-semibold text-neutral-100">{title}</span>
          <span className="rounded-full border border-neutral-700/80 bg-neutral-800/80 px-2 py-0.5 text-[11px] text-neutral-400">
            {searchText.trim() ? `${filteredModels.length}/${models.length}` : models.length}
          </span>
        </button>
        {!collapsed && models.length > 0 && (
          <div className="relative w-full sm:w-64">
            <Search
              size={14}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600"
            />
            <input
              type="search"
              value={searchText}
              onChange={event => setSearchText(event.target.value)}
              placeholder="搜索模型"
              className="h-8 w-full rounded-lg border border-neutral-800 bg-[#101010] pl-8 pr-3 text-xs text-neutral-200 outline-none transition-colors placeholder:text-neutral-600 focus:border-neutral-600"
            />
          </div>
        )}
      </div>
      {!collapsed && (
        <div className="overflow-hidden rounded-lg border border-neutral-800">
          <div
            className={`grid bg-[#101010] px-3 py-2 text-xs text-neutral-500 ${
              showDimension ? 'grid-cols-[minmax(0,1fr)_160px_112px]' : 'grid-cols-[minmax(0,1fr)_112px]'
            }`}
          >
            <span>Model (calling ID)</span>
            {showDimension && <span>Dimension</span>}
            <span className="text-center">Enable</span>
          </div>
          {filteredModels.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-neutral-500">{emptyResultText}</div>
          ) : (
            <div className="max-h-80 overflow-y-auto">
              {filteredModels.map(model => {
                const enabled = enabledSet.has(model.id)
                const toggleKey = `${providerId}:${model.id}`

                return (
                  <div
                    key={model.id}
                    className={`grid items-center border-t border-neutral-800 px-3 py-2 text-sm ${
                      showDimension ? 'grid-cols-[minmax(0,1fr)_160px_112px]' : 'grid-cols-[minmax(0,1fr)_112px]'
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="truncate text-neutral-100">{model.displayName}</div>
                      {model.displayName !== model.id && (
                        <div className="mt-0.5 truncate text-xs text-neutral-500">{model.id}</div>
                      )}
                    </div>
                    {showDimension && (
                      <span className="text-xs text-neutral-400">{model.dimension || '-'}</span>
                    )}
                    <div className="flex items-center justify-center">
                      <IconSwitch
                        checked={enabled}
                        disabled={togglingModelKey === toggleKey}
                        label={enabled ? '禁用模型' : '启用模型'}
                        onClick={() => onToggleModel(providerId, model.id)}
                      />
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DownloaderSection() {
  const [cookie, setCookie] = useState('')
  const [cookieLoading, setCookieLoading] = useState(true)
  const [cookieValidating, setCookieValidating] = useState(false)
  const [qrStarting, setQrStarting] = useState(false)
  const [qrPolling, setQrPolling] = useState(false)
  const [qrSession, setQrSession] = useState<BilibiliQrCodeSession | null>(null)
  const [qrStatus, setQrStatus] = useState<BilibiliQrCodePollResult | null>(null)
  const [cookieValidation, setCookieValidation] = useState<DownloaderCookieValidation | null>(null)
  const [proxy, setProxy] = useState<ProxyConfig | null>(null)
  const [proxyDraft, setProxyDraft] = useState({ enabled: false, url: '' })
  const [platformLoadFailed, setPlatformLoadFailed] = useState(false)

  useEffect(() => {
    const load = async () => {
      try {
        const cookieData = await getDownloaderCookie('bilibili', { silent: true })
        setCookie(cookieData?.cookie || '')
      } catch {
        setPlatformLoadFailed(true)
      } finally {
        setCookieLoading(false)
      }
    }
    load()
  }, [])

  useEffect(() => {
    const load = async () => {
      try {
        const config = await getProxyConfig({ silent: true })
        setProxy(config)
        setProxyDraft({ enabled: config.enabled, url: config.url || '' })
      } catch {
        setPlatformLoadFailed(true)
      }
    }
    load()
  }, [])

  useEffect(() => {
    if (!qrSession?.qrcode_key) return

    let cancelled = false
    let timer: number | undefined
    const intervalMs = Math.max(1, qrSession.poll_interval || 2) * 1000

    const schedule = (delay: number) => {
      timer = window.setTimeout(poll, delay)
    }

    const poll = async () => {
      setQrPolling(true)
      try {
        const result = await pollBilibiliQrCodeLogin(
          { platform: 'bilibili', qrcode_key: qrSession.qrcode_key, save: true },
          { silent: true },
        )
        if (cancelled) return

        setQrStatus(result)
        if (result.status === 'confirmed') {
          if (result.cookie) {
            setCookie(result.cookie)
          }
          setCookieValidation(result)
          toast.success(result.saved ? 'Bilibili 扫码登录成功，Cookie 已保存' : 'Bilibili 扫码已确认')
          return
        }

        if (result.status === 'expired') {
          toast.error(result.message || '二维码已过期，请重新生成')
          return
        }

        if (result.status === 'failed') {
          toast.error(result.message || '扫码登录失败，请重新生成二维码')
          return
        }

        schedule(intervalMs)
      } catch {
        if (!cancelled) schedule(intervalMs)
      } finally {
        if (!cancelled) setQrPolling(false)
      }
    }

    schedule(600)

    return () => {
      cancelled = true
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [qrSession])

  const saveCookie = async () => {
    await updateDownloaderCookie({ platform: 'bilibili', cookie })
    toast.success('Bilibili Cookie 已保存')
    await validateCookie()
  }

  const validateCookie = async () => {
    setCookieValidating(true)
    try {
      const result = await validateDownloaderCookie(
        { platform: 'bilibili', cookie },
        { silent: true },
      )
      setCookieValidation(result)
      if (result.valid) {
        toast.success('Bilibili Cookie 验证通过')
      } else {
        toast.error(result.message || 'Bilibili Cookie 未登录或已过期')
      }
    } finally {
      setCookieValidating(false)
    }
  }

  const startQrLogin = async () => {
    setQrStarting(true)
    try {
      const session = await startBilibiliQrCodeLogin('bilibili', { silent: true })
      if (!session.qrcode_key || !session.url) {
        toast.error(session.message || '生成 Bilibili 二维码失败')
        return
      }
      setQrSession(session)
      setQrStatus(null)
      setCookieValidation(null)
      toast.success('Bilibili 登录二维码已生成')
    } finally {
      setQrStarting(false)
    }
  }

  const closeQrLogin = () => {
    setQrSession(null)
    setQrStatus(null)
  }

  const saveProxy = async () => {
    const config = await updateProxyConfig(proxyDraft)
    setProxy(config)
    toast.success('代理配置已保存')
  }

  return (
    <section>
      <div className="overflow-hidden rounded-xl border border-neutral-800 bg-[#141414]">
        {platformLoadFailed && (
          <div className="border-b border-neutral-800 bg-amber-500/10 px-6 py-3 text-xs text-amber-100">
            后端配置暂未加载，当前表单仍可编辑；后端恢复后可重新进入本页刷新。
          </div>
        )}
        <div className="border-b border-neutral-800 p-6">
          <div className="mb-4">
            <div className="mb-1 font-medium text-neutral-200">Bilibili 授权 Cookie</div>
            <div className="text-xs text-neutral-500">
              配置后可抓取更稳定的字幕、音频与会员可访问内容。
            </div>
          </div>
          {cookieLoading ? (
            <div className="flex items-center gap-2 text-sm text-neutral-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              加载中...
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-col gap-3 md:flex-row md:items-center">
                <div className="flex min-w-0 flex-1 flex-col gap-3 sm:flex-row">
                  <input
                    type="password"
                    value={cookie}
                    onChange={event => {
                      setCookie(event.target.value)
                      setCookieValidation(null)
                    }}
                    placeholder="SESSDATA=..."
                    className="min-w-0 flex-1 rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 py-2 text-sm text-neutral-200 focus:border-neutral-600 focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={validateCookie}
                    disabled={cookieValidating}
                    className="inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-neutral-800 px-4 py-2 text-sm text-neutral-200 transition-colors hover:border-neutral-600 hover:bg-neutral-800 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {cookieValidating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw size={15} />}
                    验证
                  </button>
                  <button
                    type="button"
                    onClick={saveCookie}
                    className="shrink-0 rounded-lg bg-neutral-800 px-4 py-2 text-sm text-neutral-200 transition-colors hover:bg-neutral-700"
                  >
                    保存
                  </button>
                </div>
                <button
                  type="button"
                  onClick={startQrLogin}
                  disabled={qrStarting}
                  className="inline-flex h-10 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-neutral-700 bg-neutral-800 px-3 text-xs font-medium text-neutral-200 transition-colors hover:bg-neutral-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {qrStarting ? <Loader2 size={14} className="animate-spin" /> : <QrCode size={14} />}
                  扫码填入
                </button>
              </div>

              {qrSession && (
                <div className="rounded-lg border border-neutral-800 bg-[#101010] p-4">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                    <div className="flex h-[148px] w-[148px] shrink-0 items-center justify-center rounded-lg bg-white p-2">
                      <AntQRCode
                        value={qrSession.url}
                        size={132}
                        bordered={false}
                        color="#111111"
                        bgColor="#ffffff"
                      />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-neutral-800 px-3 text-xs text-neutral-400">
                          {qrPolling && <Loader2 size={13} className="animate-spin" />}
                          {qrStatus?.message || '等待扫码'}
                        </span>
                        <button
                          type="button"
                          onClick={startQrLogin}
                          disabled={qrStarting}
                          className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-neutral-800 px-3 text-xs text-neutral-300 transition-colors hover:bg-neutral-800 disabled:opacity-60"
                        >
                          {qrStarting ? <Loader2 size={13} className="animate-spin" /> : <RefreshCcw size={13} />}
                          刷新
                        </button>
                        <button
                          type="button"
                          onClick={closeQrLogin}
                          className="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-800 text-neutral-500 transition-colors hover:bg-neutral-800 hover:text-neutral-200"
                          aria-label="关闭扫码登录"
                        >
                          <X size={14} />
                        </button>
                      </div>
                      <div className="mt-3 text-xs leading-relaxed text-neutral-500">
                        {qrStatus?.status === 'confirmed'
                          ? '已自动填入并保存。'
                          : qrStatus?.status === 'scanned'
                            ? '已扫码，等待手机端确认。'
                            : qrStatus?.status === 'expired'
                              ? '二维码已过期，请刷新。'
                              : '使用 Bilibili 手机端扫码确认。'}
                      </div>
                    </div>
                  </div>
                </div>
              )}
              {cookieValidation && (
                <div
                  className={`flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs ${
                    cookieValidation.valid
                      ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-100'
                      : 'border-amber-500/30 bg-amber-500/10 text-amber-100'
                  }`}
                >
                  {cookieValidation.valid ? (
                    <CheckCircle2 size={14} className="shrink-0" />
                  ) : (
                    <X size={14} className="shrink-0" />
                  )}
                  <span>{cookieValidation.message || (cookieValidation.valid ? '已登录' : '未登录')}</span>
                  {cookieValidation.username && (
                    <span className="text-neutral-300">用户：{cookieValidation.username}</span>
                  )}
                  {cookieValidation.level != null && (
                    <span className="text-neutral-300">等级：{cookieValidation.level}</span>
                  )}
                  {cookieValidation.vip_status != null && (
                    <span className="text-neutral-300">
                      会员：{String(cookieValidation.vip_status) === '1' ? '有效' : '无'}
                    </span>
                  )}
                  {!cookieValidation.valid && cookieValidation.message?.toLowerCase().includes('dpapi') && (
                    <span className="basis-full text-amber-100/90">
                      可改用 Cookie 导出插件复制 Cookie 到输入框后保存。
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="p-6">
          <div className="mb-4">
            <div className="mb-1 font-medium text-neutral-200">全局代理</div>
            <div className="text-xs text-neutral-500">
              作用于 LLM API、转写 API 与 yt-dlp 下载。当前生效：
              {proxy?.effective || '未启用'}
            </div>
          </div>
          <div className="flex flex-col gap-3 md:flex-row md:items-center">
            <IconSwitch
              checked={proxyDraft.enabled}
              label={proxyDraft.enabled ? '禁用代理' : '启用代理'}
              onClick={() => setProxyDraft(prev => ({ ...prev, enabled: !prev.enabled }))}
              size="sm"
            />
            <input
              type="text"
              value={proxyDraft.url}
              onChange={event => setProxyDraft(prev => ({ ...prev, url: event.target.value }))}
              placeholder="http://127.0.0.1:7890"
              className="flex-1 rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 py-2 text-sm text-neutral-200 focus:border-neutral-600 focus:outline-none"
            />
            <button
              type="button"
              onClick={saveProxy}
              className="rounded-lg bg-neutral-800 px-4 py-2 text-sm text-neutral-200 transition-colors hover:bg-neutral-700"
            >
              保存代理
            </button>
          </div>
        </div>
      </div>
    </section>
  )
}

function StorageSection() {
  const storagePathConfig = useSystemStore(state => state.storagePathConfig)
  const setStoragePathConfig = useSystemStore(state => state.setStoragePathConfig)
  const resetStoragePathConfig = useSystemStore(state => state.resetStoragePathConfig)
  const markCacheClearedAt = useSystemStore(state => state.markCacheClearedAt)
  const [draft, setDraft] = useState<StoragePathConfig>(() =>
    normalizeStoragePathConfig(storagePathConfig),
  )
  const [cacheSelection, setCacheSelection] = useState<Record<CacheDirectoryKey, boolean>>(() =>
    CACHE_DIRECTORY_META.reduce(
      (selection, item) => ({
        ...selection,
        [item.key]: true,
      }),
      {} as Record<CacheDirectoryKey, boolean>,
    ),
  )
  const [, setUsageRevision] = useState(0)

  useEffect(() => {
    setDraft(normalizeStoragePathConfig(storagePathConfig))
  }, [storagePathConfig])

  const cacheStats = CACHE_DIRECTORY_META.map(item => ({
    ...item,
    path: draft.cacheDirectories[item.key] || '',
    bytes: getLocalStorageBytes(item.storageKeys),
  }))
  const selectedStats = cacheStats.filter(item => cacheSelection[item.key])
  const selectedBytes = selectedStats.reduce((total, item) => total + item.bytes, 0)
  const normalizedDraft = normalizeStoragePathConfig(draft)

  const updateDraftPath = (field: 'dataRootPath' | 'cacheRootPath', value: string) => {
    setDraft(prev => ({ ...prev, [field]: value }))
  }

  const updateCacheDirectory = (key: CacheDirectoryKey, value: string) => {
    setDraft(prev => ({
      ...prev,
      cacheDirectories: {
        ...prev.cacheDirectories,
        [key]: value,
      },
    }))
  }

  const pickDirectory = async (
    currentPath: string,
    onSelected: (path: string) => void,
  ) => {
    if (!isTauriRuntime()) {
      toast.error('系统目录选择仅在桌面端可用')
      return
    }

    try {
      const { open } = await import('@tauri-apps/plugin-dialog')
      const selected = await open({
        directory: true,
        multiple: false,
        defaultPath: currentPath || undefined,
      })
      if (typeof selected === 'string') onSelected(selected)
    } catch (error) {
      console.error('选择目录失败:', error)
      toast.error('打开系统目录选择失败')
    }
  }

  const applyCacheRoot = () => {
    setDraft(prev => ({
      ...prev,
      cacheDirectories: buildCacheDirectories(prev.cacheRootPath),
    }))
  }

  const saveStorageConfig = () => {
    const requiredPaths = [
      normalizedDraft.dataRootPath,
      normalizedDraft.cacheRootPath,
      ...Object.values(normalizedDraft.cacheDirectories),
    ]
    if (requiredPaths.some(path => !path)) {
      toast.error('请补全知识库路径和缓存目录')
      return
    }

    setStoragePathConfig(normalizedDraft)
    toast.success('存储配置已保存')
  }

  const resetStorageConfig = () => {
    const ok = window.confirm('恢复默认存储路径？当前填写的路径配置会被覆盖。')
    if (!ok) return

    resetStoragePathConfig()
    toast.success('已恢复默认存储路径')
  }

  const clearSelectedCache = () => {
    if (selectedStats.length === 0) {
      toast.error('请选择要清理的缓存类型')
      return
    }

    const ok = window.confirm('清理所选缓存？不会删除知识库文件夹、笔记或任务。')
    if (!ok) return

    if (typeof localStorage !== 'undefined') {
      selectedStats.forEach(item => {
        item.storageKeys.forEach(key => localStorage.removeItem(key))
      })
    }
    markCacheClearedAt(new Date().toISOString())
    setUsageRevision(value => value + 1)
    toast.success('已清理所选缓存')
  }

  return (
    <section className="space-y-4">
      <div className="rounded-xl border border-neutral-800 bg-[#141414] p-6">
        <div className="mb-5 flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="font-medium text-neutral-200">数据与缓存路径</div>
            <div className="mt-1 text-xs text-neutral-500">
              当前客户端的本地路径偏好。
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={resetStorageConfig}
              className="flex items-center gap-1.5 rounded-lg border border-neutral-800 px-3 py-2 text-xs text-neutral-400 transition-colors hover:bg-neutral-800 hover:text-neutral-200"
            >
              <RefreshCcw size={14} />
              恢复默认
            </button>
            <button
              type="button"
              onClick={saveStorageConfig}
              className="flex items-center gap-1.5 rounded-lg bg-neutral-200 px-3 py-2 text-xs font-semibold text-neutral-950 transition-colors hover:bg-white"
            >
              <Save size={14} />
              保存路径
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label className="mb-2 block text-xs font-medium text-neutral-400">数据根目录</label>
            <PathPickerInput
              value={draft.dataRootPath}
              placeholder="./data"
              onChange={value => updateDraftPath('dataRootPath', value)}
              onPick={() =>
                pickDirectory(draft.dataRootPath, value =>
                  updateDraftPath('dataRootPath', value),
                )
              }
            />
          </div>
          <div>
            <label className="mb-2 block text-xs font-medium text-neutral-400">缓存根目录</label>
            <div className="flex gap-2">
              <PathPickerInput
                value={draft.cacheRootPath}
                placeholder="./data/cache"
                onChange={value => updateDraftPath('cacheRootPath', value)}
                onPick={() =>
                  pickDirectory(draft.cacheRootPath, value => updateDraftPath('cacheRootPath', value))
                }
              />
              <button
                type="button"
                onClick={applyCacheRoot}
                className="shrink-0 rounded-lg border border-neutral-800 px-3 py-2 text-xs text-neutral-400 transition-colors hover:bg-neutral-800 hover:text-neutral-200"
              >
                生成子目录
              </button>
            </div>
          </div>
        </div>

        <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2">
          {CACHE_DIRECTORY_META.map(item => (
            <div key={item.key}>
              <label className="mb-2 block text-xs font-medium text-neutral-400">
                {item.label}目录
              </label>
              <PathPickerInput
                value={draft.cacheDirectories[item.key]}
                onChange={value => updateCacheDirectory(item.key, value)}
                onPick={() =>
                  pickDirectory(draft.cacheDirectories[item.key], value =>
                    updateCacheDirectory(item.key, value),
                  )
                }
              />
            </div>
          ))}
        </div>
      </div>

      <div className="rounded-xl border border-neutral-800 bg-[#141414] p-6">
        <div className="mb-5 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <div className="font-medium text-neutral-200">清理缓存</div>
            <div className="mt-1 text-xs text-neutral-500">
              上次清理：{formatCacheClearedAt(storagePathConfig.lastCacheClearedAt)}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => setUsageRevision(value => value + 1)}
              className="flex items-center gap-1.5 rounded-lg border border-neutral-800 px-3 py-2 text-xs text-neutral-400 transition-colors hover:bg-neutral-800 hover:text-neutral-200"
            >
              <RefreshCcw size={14} />
              重新统计
            </button>
            <button
              type="button"
              onClick={clearSelectedCache}
              className="flex items-center gap-1.5 rounded-lg bg-red-500/15 px-3 py-2 text-xs font-semibold text-red-300 transition-colors hover:bg-red-500/25"
            >
              <Trash2 size={14} />
              清理所选
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {cacheStats.map(item => (
            <label
              key={item.key}
              className="flex cursor-pointer gap-3 rounded-lg border border-neutral-800 bg-[#1A1A1A] p-4 transition-colors hover:border-neutral-700"
            >
              <input
                type="checkbox"
                checked={cacheSelection[item.key]}
                onChange={event =>
                  setCacheSelection(prev => ({ ...prev, [item.key]: event.target.checked }))
                }
                className="mt-1 h-4 w-4 rounded border-neutral-700 bg-neutral-950 accent-primary"
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium text-neutral-200">{item.label}</span>
                  <span className="shrink-0 text-xs text-neutral-500">
                    {formatBytes(item.bytes)}
                  </span>
                </span>
                <span className="mt-1 block text-xs leading-relaxed text-neutral-500">
                  {item.detail}
                </span>
                <span className="mt-2 block truncate font-mono text-[11px] text-neutral-600">
                  {item.path || '未设置'}
                </span>
              </span>
            </label>
          ))}
        </div>

        <div className="mt-4 rounded-lg border border-neutral-800 bg-[#101010] px-4 py-3 text-xs text-neutral-500">
          已选 {selectedStats.length} 类，预计清理 {formatBytes(selectedBytes)}
        </div>
      </div>
    </section>
  )
}

function PathPickerInput({
  value,
  placeholder,
  onChange,
  onPick,
}: {
  value: string
  placeholder?: string
  onChange: (value: string) => void
  onPick: () => void
}) {
  const canPickDirectory = isTauriRuntime()

  return (
    <div className="flex min-w-0 flex-1 gap-2">
      <input
        type="text"
        value={value}
        onChange={event => onChange(event.target.value)}
        placeholder={placeholder}
        className="min-w-0 flex-1 rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 py-2 text-sm text-neutral-200 outline-none focus:border-neutral-600"
      />
      <button
        type="button"
        onClick={onPick}
        disabled={!canPickDirectory}
        title={canPickDirectory ? '选择目录' : '桌面端可用'}
        className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-neutral-800 text-neutral-400 transition-colors hover:bg-neutral-800 hover:text-neutral-200 disabled:cursor-not-allowed disabled:opacity-40"
        aria-label="选择目录"
      >
        <FolderSearch size={16} />
      </button>
    </div>
  )
}

const isWhisperType = (type: string) => type === 'fast-whisper' || type === 'mlx-whisper'

const fallbackTranscriberConfig: TranscriberConfig = {
  transcriber_type: 'fast-whisper',
  whisper_model_size: 'base',
  available_types: [
    { value: 'fast-whisper', label: 'fast-whisper' },
    { value: 'mlx-whisper', label: 'mlx-whisper' },
  ],
  whisper_model_sizes: ['tiny', 'base', 'small', 'medium', 'large-v3'],
  mlx_whisper_available: false,
}

function TranscriberSection() {
  const [config, setConfig] = useState<TranscriberConfig | null>(null)
  const [modelStatuses, setModelStatuses] = useState<ModelStatus[]>([])
  const [selectedType, setSelectedType] = useState('')
  const [selectedModel, setSelectedModel] = useState('')
  const [saving, setSaving] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)
  const [downloadProgress, setDownloadProgress] = useState<Record<string, number>>({})

  const load = async (silent = false) => {
    try {
      const [cfg, statuses] = await Promise.all([
        getTranscriberConfig(silent ? { silent: true } : undefined),
        getModelsStatus(silent ? { silent: true } : undefined),
      ])
      setConfig(cfg)
      setSelectedType(cfg.transcriber_type)
      setSelectedModel(cfg.whisper_model_size)
      setModelStatuses(statuses.whisper)
      setLoadFailed(false)
    } catch {
      setConfig(fallbackTranscriberConfig)
      setSelectedType(current => current || fallbackTranscriberConfig.transcriber_type)
      setSelectedModel(current => current || fallbackTranscriberConfig.whisper_model_size)
      setModelStatuses([])
      setLoadFailed(true)
    }
  }

  // 只刷新模型状态，不重置用户选择
  const refreshStatus = async () => {
    try {
      const statuses = await getModelsStatus({ silent: true })
      setModelStatuses(statuses.whisper)
    } catch {
      // 静默失败
    }
  }

  useEffect(() => {
    load(true)
  }, [])

  // 下载进度轮询：当有模型正在下载时，每 1.5 秒查询进度
  useEffect(() => {
    const downloadingModels = modelStatuses.filter(s => s.downloading)
    if (downloadingModels.length === 0) return

    const interval = setInterval(async () => {
      for (const model of downloadingModels) {
        try {
          const progress = await getDownloadProgress(model.model_size, { silent: true })
          if (progress) {
            setDownloadProgress(prev => ({
              ...prev,
              [model.model_size]: progress.progress,
            }))
            // 下载完成或失败时刷新状态（不重置选择）
            if (!progress.downloading) {
              refreshStatus()
              setDownloadProgress(prev => {
                const next = { ...prev }
                delete next[model.model_size]
                return next
              })
            }
          }
        } catch {
          // 静默失败
        }
      }
    }, 1500)

    return () => clearInterval(interval)
  }, [modelStatuses])

  const currentStatus = useMemo(
    () => modelStatuses.find(status => status.model_size === selectedModel),
    [modelStatuses, selectedModel],
  )

  const currentProgress = downloadProgress[selectedModel] ?? 0

  const save = async () => {
    setSaving(true)
    try {
      await updateTranscriberConfig({
        transcriber_type: selectedType,
        whisper_model_size: isWhisperType(selectedType) ? selectedModel : undefined,
      })
      toast.success('转写器配置已保存')
    } finally {
      setSaving(false)
    }
  }

  return (
    <section>
      <div className="rounded-xl border border-neutral-800 bg-[#141414] p-6">
        {!config ? (
          <div className="flex items-center gap-2 text-sm text-neutral-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            加载中...
          </div>
        ) : (
          <div className="space-y-5">
            {loadFailed && (
              <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-xs text-amber-100">
                转写配置暂未从后端加载，当前显示前端默认选项。
              </div>
            )}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <label className="mb-2 block text-xs font-medium text-neutral-400">转写器类型</label>
                <select
                  value={selectedType}
                  onChange={event => setSelectedType(event.target.value)}
                  className="w-full rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 py-2 text-sm text-neutral-200 outline-none"
                >
                  {config.available_types.map(type => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
              </div>

              {isWhisperType(selectedType) && (
                <div>
                  <label className="mb-2 block text-xs font-medium text-neutral-400">
                    Whisper 模型
                  </label>
                  <select
                    value={selectedModel}
                    onChange={event => setSelectedModel(event.target.value)}
                    className="w-full rounded-lg border border-neutral-800 bg-[#1A1A1A] px-3 py-2 text-sm text-neutral-200 outline-none"
                  >
                    {config.whisper_model_sizes.map(size => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {isWhisperType(selectedType) && currentStatus && (
              <div className="flex flex-col gap-2 rounded-lg border border-neutral-800 bg-[#1A1A1A] p-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium text-neutral-200">{selectedModel}</div>
                    <div className="mt-1 text-xs text-neutral-500">
                      {currentStatus.downloaded
                        ? '模型已就绪'
                        : currentStatus.downloading
                          ? `模型下载中 ${currentProgress > 0 ? `${currentProgress.toFixed(1)}%` : ''}`
                          : currentStatus.failed
                            ? currentStatus.error || '模型下载失败'
                            : '模型尚未下载'}
                    </div>
                  </div>
                  {!currentStatus.downloaded && !currentStatus.downloading && (
                    <button
                      type="button"
                      onClick={async () => {
                        const result = await downloadModel({ model_size: selectedModel, transcriber_type: selectedType })
                        if (isSkippedApiResult(result)) {
                          toast.success('后端模型下载接口暂未实现，已跳过')
                        } else {
                          toast.success('模型下载已开始')
                        }
                        setTimeout(() => refreshStatus(), 800)
                      }}
                      className="flex items-center gap-1.5 rounded-lg bg-neutral-800 px-3 py-2 text-xs text-neutral-200 transition-colors hover:bg-neutral-700"
                    >
                      <Download size={14} />
                      {currentStatus.failed ? '重试' : '下载'}
                    </button>
                  )}
                  {currentStatus.downloading && (
                    <Loader2 size={16} className="animate-spin text-neutral-400" />
                  )}
                </div>
                {currentStatus.downloading && currentProgress > 0 && (
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-neutral-800">
                    <div
                      className="h-full rounded-full bg-primary transition-all duration-500"
                      style={{ width: `${Math.min(currentProgress, 100)}%` }}
                    />
                  </div>
                )}
              </div>
            )}

            <button
              type="button"
              onClick={save}
              disabled={saving}
              className="flex items-center gap-1.5 rounded-lg bg-neutral-800 px-4 py-2 text-sm text-neutral-200 transition-colors hover:bg-neutral-700 disabled:opacity-50"
            >
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              保存配置
            </button>
          </div>
        )}
      </div>
    </section>
  )
}

function MonitorSection() {
  const [status, setStatus] = useState<DeployStatus | null>(null)
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)

  const load = async (silent = false) => {
    setLoading(true)
    try {
      const opts = silent ? { silent: true } : undefined
      const [deployStatus, systemStats] = await Promise.all([
        getDeployStatus(opts),
        getSystemStats(opts),
      ])
      setStatus(deployStatus)
      setStats(systemStats)
      setLoadFailed(false)
    } catch {
      setStatus(null)
      setStats(null)
      setLoadFailed(true)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load(true)
  }, [])

  const backendOk = status?.backend.status === 'ok' || status?.backend.status === 'running'

  return (
    <section>
      <div className="mb-4 flex justify-end">
        <button
          type="button"
          onClick={() => load()}
          disabled={loading}
          className="rounded-lg bg-neutral-800 px-3 py-1.5 text-xs text-neutral-300 transition-colors hover:bg-neutral-700 disabled:opacity-50"
        >
          {loading ? '刷新中...' : '刷新'}
        </button>
      </div>
      {loadFailed && (
        <div className="mb-4 rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-xs text-amber-100">
          运行状态暂未加载，后端恢复后可手动刷新。
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatusCard
          icon={<Server size={18} />}
          title="后端"
          value={backendOk ? `${status?.backend.status}:${status?.backend.port}` : '未知'}
          ok={backendOk}
        />
        <StatusCard
          icon={<Settings2 size={18} />}
          title="FFmpeg"
          value={status?.ffmpeg.available ? '可用' : '不可用'}
          ok={status?.ffmpeg.available}
        />
        <StatusCard
          icon={<HardDrive size={18} />}
          title="转写"
          value={
            status
              ? `${status.whisper.transcriber_type || 'unknown'} / ${status.whisper.model_size || '-'}`
              : '未知'
          }
          ok={status ? true : undefined}
        />
        <StatusCard
          icon={<Database size={18} />}
          title="CUDA"
          value={status?.cuda.available ? status.cuda.gpu_name || '已启用' : '未启用'}
          ok={status?.cuda.available}
        />
        <StatusCard
          icon={<VideoIcon size={18} />}
          title="视频"
          value={`${stats?.completed_videos ?? 0}/${stats?.total_videos ?? 0} 已完成`}
          ok={stats ? true : undefined}
        />
        <StatusCard
          icon={<FileTextIcon size={18} />}
          title="笔记"
          value={`${stats?.total_notes ?? 0} 篇 / ${stats?.total_chunks ?? 0} chunks`}
          ok={stats ? true : undefined}
        />
        <StatusCard
          icon={<Database size={18} />}
          title="存储"
          value={`${formatBytes(stats?.storage_usage_bytes ?? 0)} 已用，${formatBytes(stats?.disk_free_bytes ?? 0)} 可用`}
          ok={stats ? true : undefined}
        />
        <StatusCard
          icon={<Activity size={18} />}
          title="时长"
          value={`${stats?.total_duration_hours ?? 0} 小时`}
          ok={stats ? true : undefined}
        />
      </div>
    </section>
  )
}

function StatusCard({
  icon,
  title,
  value,
  ok,
}: {
  icon: ReactNode
  title: string
  value: string
  ok?: boolean
}) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-[#141414] p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-medium text-neutral-300">
          {icon}
          {title}
        </div>
        {ok !== undefined && (
          <span className={ok ? 'text-primary' : 'text-red-400'}>
            <CheckCircle2 size={16} />
          </span>
        )}
      </div>
      <div className="truncate text-sm text-neutral-500">{value}</div>
    </div>
  )
}
