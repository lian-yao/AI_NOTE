import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { QRCode as AntQRCode } from 'antd'
import toast from 'react-hot-toast'
import {
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Download,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  MessageSquareText,
  QrCode,
  RefreshCcw,
  Save,
  Search,
  Server,
  ShieldCheck,
  X,
} from 'lucide-react'
import logo from '@/assets/icon.svg'
import type { IProvider } from '@/types'
import {
  addModel,
  addProvider,
  fetchModels,
  getProviderList,
  testConnection,
  updateProviderById,
} from '@/services/model'
import {
  downloadModel,
  getDownloadProgress,
  getModelsStatus,
  getTranscriberConfig,
  updateTranscriberConfig,
  type ModelStatus,
  type TranscriberConfig,
} from '@/services/transcriber'
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
import { isSkippedApiResult } from '@/services/fallback'
import { updateModelUsageConfig } from '@/services/system'
import { getApiBaseURL } from '@/utils/api'
import { markOnboardingComplete } from '@/utils/onboarding'

const steps = [
  { id: 'backend', label: '后端连通', title: '检测本地后端', icon: Server },
  { id: 'provider', label: '模型服务', title: '配置 Provider', icon: KeyRound },
  { id: 'transcriber', label: '本地转写', title: '选择转写模型', icon: MessageSquareText },
  { id: 'cookie', label: 'B 站授权', title: 'Bilibili Cookie', icon: QrCode },
] as const

type StepId = typeof steps[number]['id']
type ProviderPreset = {
  id: string
  label: string
  name: string
  logo: string
  baseUrl: string
  description: string
}
type RemoteModel = { id: string; displayName: string; dimension?: string | number }

const providerPresets: ProviderPreset[] = [
  {
    id: 'deepseek',
    label: 'DeepSeek',
    name: 'DeepSeek',
    logo: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com/v1',
    description: 'OpenAI 兼容接口，适合中文问答与长文本分析。',
  },
  {
    id: 'qwen',
    label: 'Qwen',
    name: 'Qwen',
    logo: 'Qwen',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    description: '阿里云 DashScope 兼容模式，适合通义模型。',
  },
  {
    id: 'openai',
    label: 'OpenAI',
    name: 'OpenAI',
    logo: 'OpenAI',
    baseUrl: 'https://api.openai.com/v1',
    description: 'OpenAI 官方或兼容转发网关。',
  },
  {
    id: 'gemini',
    label: 'Gemini',
    name: 'Gemini',
    logo: 'Gemini',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    description: 'Gemini OpenAI 兼容接口。',
  },
  {
    id: 'custom',
    label: '自定义',
    name: 'Custom Provider',
    logo: 'custom',
    baseUrl: '',
    description: '本地模型网关、代理服务或其它兼容端点。',
  },
]

const fallbackTranscriberConfig: TranscriberConfig = {
  transcriber_type: 'fast-whisper',
  whisper_model_size: 'small',
  whisper_device: 'auto',
  available_types: [{ value: 'fast-whisper', label: 'fast-whisper' }],
  whisper_model_sizes: ['tiny', 'base', 'small', 'medium', 'large-v3', 'turbo'],
  mlx_whisper_available: false,
}

const modelFallbackMeta: Record<string, { size: string; repo: string }> = {
  tiny: { size: '约 75 MB', repo: 'Systran/faster-whisper-tiny' },
  base: { size: '约 145 MB', repo: 'Systran/faster-whisper-base' },
  small: { size: '约 466 MB', repo: 'Systran/faster-whisper-small' },
  medium: { size: '约 1.5 GB', repo: 'Systran/faster-whisper-medium' },
  'large-v3': { size: '约 3.0 GB', repo: 'Systran/faster-whisper-large-v3' },
  turbo: { size: '约 1.6 GB', repo: 'mobiuslabsgmbh/faster-whisper-large-v3-turbo' },
}

function markOnboarded() {
  markOnboardingComplete()
}

function errText(error: unknown): string {
  if (!error) return '未知错误'
  if (typeof error === 'string') return error
  if (error instanceof Error) return error.message
  if (typeof error === 'object') {
    const item = error as { detail?: unknown; message?: unknown; msg?: unknown }
    if (typeof item.msg === 'string') return item.msg
    if (typeof item.message === 'string') return item.message
    if (typeof item.detail === 'string') return item.detail
    try {
      return JSON.stringify(error)
    } catch {
      return '未知错误'
    }
  }
  return String(error)
}

async function pingBackend(): Promise<boolean> {
  try {
    const response = await fetch(`${getApiBaseURL()}/system/ready`, { cache: 'no-store' })
    if (response.status === 404) return true
    if (!response.ok) return false
    const json = await response.json().catch(() => null)
    return json?.code === 0 && json?.data?.ready !== false
  } catch {
    return false
  }
}

function remoteModelId(model: unknown): string {
  if (typeof model === 'string') return model
  if (!model || typeof model !== 'object') return ''
  const item = model as Record<string, unknown>
  const id = item.id || item.model || item.name || item.model_name
  return typeof id === 'string' ? id : ''
}

function normalizeRemoteModels(response: unknown): RemoteModel[] {
  const root = response as { data?: unknown; models?: unknown } | undefined
  const rawModels = Array.isArray(root?.models)
    ? root.models
    : Array.isArray((root?.models as { data?: unknown[] } | undefined)?.data)
      ? (root?.models as { data?: unknown[] }).data
      : Array.isArray(root?.data)
        ? root.data
        : Array.isArray(response)
          ? response
          : []

  const map = new Map<string, RemoteModel>()
  rawModels.forEach(raw => {
    const id = remoteModelId(raw)
    if (!id || map.has(id)) return
    const item = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
    const dimension = item.dimension || item.dimensions || item.embedding_dimensions
    map.set(id, {
      id,
      displayName: typeof item.display_name === 'string' ? item.display_name : id,
      dimension:
        typeof dimension === 'string' || typeof dimension === 'number'
          ? dimension
          : undefined,
    })
  })
  return [...map.values()].sort((a, b) => a.id.localeCompare(b.id))
}

function isEmbeddingModel(modelName: string) {
  const lower = modelName.toLowerCase()
  return lower.includes('embed') || lower.includes('embedding') || lower.includes('bge')
}

function formatBytes(bytes?: number | null) {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex += 1
  }
  const precision = value >= 10 || unitIndex === 0 ? 0 : 1
  return `${value.toFixed(precision)} ${units[unitIndex]}`
}

function modelSizeLabel(status: ModelStatus | undefined, modelSize: string) {
  if (status?.estimated_size_label) return status.estimated_size_label
  if (status?.estimated_size_mb) return `约 ${status.estimated_size_mb} MB`
  return modelFallbackMeta[modelSize]?.size || '未知大小'
}

function modelRepoLabel(status: ModelStatus | undefined, modelSize: string) {
  return status?.repo_id || modelFallbackMeta[modelSize]?.repo || modelSize
}

function modelState(status: ModelStatus | undefined, progress?: number) {
  if (!status) {
    return {
      label: '未扫描',
      className: 'border-slate-200 bg-slate-50 text-slate-500',
    }
  }
  if (status.downloaded) {
    const size = status.downloaded_size_bytes || status.cache_size_bytes
    return {
      label: size ? `已缓存 ${formatBytes(size)}` : '已缓存',
      className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    }
  }
  if (status.downloading) {
    return {
      label: progress ? `下载中 ${Math.round(progress)}%` : '下载中',
      className: 'border-sky-200 bg-sky-50 text-sky-700',
    }
  }
  if (status.partial) {
    return {
      label: `未完整 ${formatBytes(status.partial_size_bytes || status.cache_size_bytes)}`,
      className: 'border-amber-200 bg-amber-50 text-amber-700',
    }
  }
  if (status.failed) {
    return {
      label: status.error || '下载失败',
      className: 'border-red-200 bg-red-50 text-red-700',
    }
  }
  return {
    label: '未下载',
    className: 'border-slate-200 bg-slate-50 text-slate-500',
  }
}

export default function Onboarding() {
  const navigate = useNavigate()
  const [activeStep, setActiveStep] = useState<StepId>('backend')
  const [error, setError] = useState('')

  const [pinging, setPinging] = useState(false)
  const [backendOk, setBackendOk] = useState<boolean | null>(null)

  const [presetId, setPresetId] = useState(providerPresets[0].id)
  const currentPreset = useMemo(
    () => providerPresets.find(item => item.id === presetId) || providerPresets[0],
    [presetId],
  )
  const [providerName, setProviderName] = useState(providerPresets[0].name)
  const [baseUrl, setBaseUrl] = useState(providerPresets[0].baseUrl)
  const [apiKey, setApiKey] = useState('')
  const [showApiKey, setShowApiKey] = useState(false)
  const [providerId, setProviderId] = useState('')
  const [remoteModels, setRemoteModels] = useState<RemoteModel[]>([])
  const [selectedModels, setSelectedModels] = useState<string[]>([])
  const [manualModelName, setManualModelName] = useState('')
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelFetchAttempted, setModelFetchAttempted] = useState(false)
  const [providerSaving, setProviderSaving] = useState(false)

  const [transcriberConfig, setTranscriberConfig] = useState<TranscriberConfig | null>(null)
  const [modelStatuses, setModelStatuses] = useState<ModelStatus[]>([])
  const [selectedModel, setSelectedModel] = useState('')
  const [selectedDevice, setSelectedDevice] = useState('auto')
  const [transcriberLoading, setTranscriberLoading] = useState(false)
  const [transcriberSaving, setTranscriberSaving] = useState(false)
  const [statusRefreshing, setStatusRefreshing] = useState(false)
  const [activeDownloads, setActiveDownloads] = useState<string[]>([])
  const [downloadProgress, setDownloadProgress] = useState<Record<string, number>>({})

  const [cookie, setCookie] = useState('')
  const [cookieLoaded, setCookieLoaded] = useState(false)
  const [cookieLoading, setCookieLoading] = useState(false)
  const [cookieSaving, setCookieSaving] = useState(false)
  const [cookieValidation, setCookieValidation] =
    useState<DownloaderCookieValidation | null>(null)
  const [qrStarting, setQrStarting] = useState(false)
  const [qrPolling, setQrPolling] = useState(false)
  const [qrSession, setQrSession] = useState<BilibiliQrCodeSession | null>(null)
  const [qrStatus, setQrStatus] = useState<BilibiliQrCodePollResult | null>(null)

  const stepIndex = steps.findIndex(step => step.id === activeStep)
  const canGoBack = stepIndex > 0

  const finish = () => {
    markOnboarded()
    navigate('/', { replace: true })
  }

  const goToStep = (stepId: StepId) => {
    setError('')
    setActiveStep(stepId)
  }

  const nextStep = () => {
    const next = steps[stepIndex + 1]
    if (next) goToStep(next.id)
  }

  const prevStep = () => {
    const prev = steps[stepIndex - 1]
    if (prev) goToStep(prev.id)
  }

  const doPing = useCallback(async () => {
    setPinging(true)
    const ok = await pingBackend()
    setBackendOk(ok)
    setPinging(false)
    return ok
  }, [])

  useEffect(() => {
    let cancelled = false
    let retryTimer: number | undefined
    let offReady: (() => void) | undefined
    let offRestarted: (() => void) | undefined

    ;(async () => {
      const ok = await doPing()
      if (cancelled) return
      if (!ok) {
        retryTimer = window.setTimeout(() => {
          if (!cancelled) doPing()
        }, 1800)
      }

      if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
        try {
          const { listen } = await import('@tauri-apps/api/event')
          offReady = await listen('backend-ready', () => {
            if (!cancelled) doPing()
          })
          offRestarted = await listen('backend-restarted', () => {
            if (!cancelled) doPing()
          })
        } catch {
          // Tauri event bridge may be unavailable in pure browser preview.
        }
      }
    })()

    return () => {
      cancelled = true
      if (retryTimer) window.clearTimeout(retryTimer)
      offReady?.()
      offRestarted?.()
    }
  }, [doPing])

  useEffect(() => {
    if (activeStep === 'transcriber' && !transcriberConfig) {
      loadTranscriberState(true)
    }
  }, [activeStep, transcriberConfig])

  useEffect(() => {
    if (activeStep === 'cookie' && !cookieLoaded && !cookieLoading) {
      loadCookie()
    }
  }, [activeStep, cookieLoaded, cookieLoading])

  useEffect(() => {
    const pollingModels = Array.from(
      new Set([
        ...activeDownloads,
        ...modelStatuses
          .filter(status => status.downloading)
          .map(status => status.model_size),
      ]),
    )
    if (pollingModels.length === 0) return

    const timer = window.setInterval(async () => {
      for (const modelSize of pollingModels) {
        try {
          const progress = await getDownloadProgress(modelSize, { silent: true })
          setDownloadProgress(prev => ({
            ...prev,
            [modelSize]: progress.progress || 0,
          }))
          if (!progress.downloading) {
            setActiveDownloads(prev => prev.filter(item => item !== modelSize))
            setDownloadProgress(prev => {
              const next = { ...prev }
              delete next[modelSize]
              return next
            })
            await refreshModelStatus()
          }
        } catch {
          // Polling is best-effort; the next scan will recover state.
        }
      }
    }, 1500)

    return () => window.clearInterval(timer)
  }, [activeDownloads, modelStatuses])

  useEffect(() => {
    if (!qrSession?.qrcode_key) return
    let cancelled = false
    let timer: number | undefined
    const intervalMs = Math.max(1, qrSession.poll_interval || 2) * 1000

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
          if (result.cookie) setCookie(result.cookie)
          setCookieValidation(result)
          toast.success(result.saved ? 'Bilibili Cookie 已保存' : 'Bilibili 已确认登录')
          return
        }
        if (result.status === 'expired') {
          toast.error(result.message || '二维码已过期')
          return
        }
        if (result.status === 'failed') {
          toast.error(result.message || '扫码登录失败')
          return
        }
        timer = window.setTimeout(poll, intervalMs)
      } catch {
        if (!cancelled) timer = window.setTimeout(poll, intervalMs)
      } finally {
        if (!cancelled) setQrPolling(false)
      }
    }

    timer = window.setTimeout(poll, 600)
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [qrSession])

  const applyPreset = (preset: ProviderPreset) => {
    setPresetId(preset.id)
    setProviderName(preset.name)
    setBaseUrl(preset.baseUrl)
    setProviderId('')
    setRemoteModels([])
    setSelectedModels([])
    setManualModelName('')
    setModelFetchAttempted(false)
    setError('')
  }

  const saveProviderBase = async () => {
    const name = providerName.trim()
    const url = baseUrl.trim().replace(/\/+$/, '')
    const key = apiKey.trim()
    if (!name) throw new Error('请填写 Provider 名称')
    if (!url) throw new Error('请选择模板或填写 Base URL')
    if (!key) throw new Error('请填写 API Key')

    const existingProviders = await getProviderList({ silent: true }).catch(
      () => [] as IProvider[],
    )
    const existing = existingProviders.find(
      provider => provider.name.trim().toLowerCase() === name.toLowerCase(),
    )
    if (existing?.id) {
      await updateProviderById(
        {
          id: existing.id,
          name,
          logo: currentPreset.logo,
          type: 'openai-compatible',
          base_url: url,
          api_key: key,
          enabled: 1,
        },
        { silent: true },
      )
      setProviderId(existing.id)
      return existing.id
    }

    const id = await addProvider(
      {
        name,
        logo: currentPreset.logo,
        type: 'openai-compatible',
        base_url: url,
        api_key: key,
        enabled: 1,
      },
      { silent: true },
    )
    setProviderId(id)
    return id
  }

  const fetchRemoteModelList = async () => {
    setError('')
    setModelsLoading(true)
    setModelFetchAttempted(true)
    try {
      const id = await saveProviderBase()
      const response = await fetchModels(id, { silent: true })
      const models = normalizeRemoteModels(response)
      setRemoteModels(models)
      setSelectedModels(prev => {
        const validPrev = prev.filter(model => models.some(item => item.id === model))
        if (validPrev.length > 0) return validPrev
        return models.slice(0, 1).map(model => model.id)
      })
      if (models.length > 0) {
        toast.success(`已从 Provider 获取 ${models.length} 个模型`)
      } else {
        toast.error('Provider 接口未返回模型列表，可在下方手动填写模型名')
      }
    } catch (error) {
      setRemoteModels([])
      setSelectedModels([])
      setError(`获取模型失败：${errText(error)}`)
    } finally {
      setModelsLoading(false)
    }
  }

  const toggleModel = (modelId: string) => {
    setSelectedModels(prev =>
      prev.includes(modelId)
        ? prev.filter(item => item !== modelId)
        : [...prev, modelId],
    )
  }

  const modelsToSave = useMemo(() => {
    const manual = manualModelName.trim()
    const set = new Set(selectedModels)
    if (manual) set.add(manual)
    return [...set]
  }, [manualModelName, selectedModels])

  const saveProviderAndContinue = async () => {
    setError('')
    if (modelsToSave.length === 0) {
      setError('请先点击“获取模型”选择模型，或手动填写一个模型名')
      return
    }

    setProviderSaving(true)
    try {
      const id = await saveProviderBase()
      for (const model of modelsToSave) {
        try {
          await addModel({ provider_id: id, model_name: model }, { silent: true })
        } catch (modelError) {
          const message = errText(modelError)
          if (!message.includes('已存在')) throw modelError
        }
      }
      const qaModel = modelsToSave.find(model => !isEmbeddingModel(model)) || modelsToSave[0]
      await updateModelUsageConfig({ qa_provider_id: id, qa_model_name: qaModel }).catch(
        () => undefined,
      )
      await testConnection({ id, model: qaModel }, { silent: true }).catch(() => undefined)
      toast.success('Provider 和默认模型已保存')
      nextStep()
    } catch (error) {
      setError(`保存失败：${errText(error)}`)
    } finally {
      setProviderSaving(false)
    }
  }

  const loadTranscriberState = async (silent = false) => {
    setTranscriberLoading(true)
    try {
      const [config, statuses] = await Promise.all([
        getTranscriberConfig(silent ? { silent: true } : undefined),
        getModelsStatus(silent ? { silent: true } : undefined),
      ])
      setTranscriberConfig(config)
      setModelStatuses(statuses.whisper)
      setSelectedModel(current => current || config.whisper_model_size || 'small')
      setSelectedDevice(config.whisper_device || 'auto')
    } catch {
      setTranscriberConfig(fallbackTranscriberConfig)
      setSelectedModel(current => current || fallbackTranscriberConfig.whisper_model_size)
      setSelectedDevice(fallbackTranscriberConfig.whisper_device)
      setModelStatuses([])
    } finally {
      setTranscriberLoading(false)
    }
  }

  const refreshModelStatus = async (showToast = false) => {
    setStatusRefreshing(showToast)
    try {
      const statuses = await getModelsStatus({ silent: true })
      setModelStatuses(statuses.whisper)
      if (showToast) toast.success('已重新扫描模型缓存')
    } catch {
      if (showToast) toast.error('模型缓存扫描失败')
    } finally {
      setStatusRefreshing(false)
    }
  }

  const startModelDownload = async (modelSize: string) => {
    setError('')
    try {
      const result = await downloadModel({ model_size: modelSize, transcriber_type: 'fast-whisper' })
      if (isSkippedApiResult(result)) {
        toast.success('后端下载接口暂未实现，已跳过')
        return
      }
      const payload = result as { message?: string; status?: string }
      if (payload.status === 'already_downloaded') toast.success('模型已在本地缓存中')
      else if (payload.status === 'already_downloading') {
        toast.success(payload.message || '模型正在下载')
      } else if (payload.status === 'error') {
        toast.error(payload.message || '模型下载启动失败')
      } else {
        toast.success('模型下载已开始')
      }
      setActiveDownloads(prev => (prev.includes(modelSize) ? prev : [...prev, modelSize]))
      window.setTimeout(() => refreshModelStatus(), 800)
    } catch (error) {
      setError(`下载失败：${errText(error)}`)
    }
  }

  const saveTranscriberAndContinue = async () => {
    setError('')
    setTranscriberSaving(true)
    try {
      await updateTranscriberConfig({
        transcriber_type: transcriberConfig?.transcriber_type || 'fast-whisper',
        whisper_model_size: selectedModel,
        whisper_device: selectedDevice,
      })
      toast.success('转写模型配置已保存')
      nextStep()
    } catch (error) {
      setError(`保存失败：${errText(error)}`)
    } finally {
      setTranscriberSaving(false)
    }
  }

  const loadCookie = async () => {
    setCookieLoading(true)
    try {
      const cookieData = await getDownloaderCookie('bilibili', { silent: true })
      setCookie(cookieData?.cookie || '')
    } catch {
      // Cookie is optional.
    } finally {
      setCookieLoaded(true)
      setCookieLoading(false)
    }
  }

  const validateCookieValue = async () => {
    setError('')
    setCookieSaving(true)
    try {
      const result = await validateDownloaderCookie({ platform: 'bilibili', cookie }, { silent: true })
      setCookieValidation(result)
      if (result.valid) toast.success('Bilibili Cookie 验证通过')
      else setError(result.message || 'Cookie 未登录或已过期')
      return result.valid
    } catch (error) {
      setError(`验证失败：${errText(error)}`)
      return false
    } finally {
      setCookieSaving(false)
    }
  }

  const saveCookieAndFinish = async () => {
    setError('')
    if (!cookie.trim()) {
      finish()
      return
    }

    setCookieSaving(true)
    try {
      await updateDownloaderCookie({ platform: 'bilibili', cookie })
      const result = await validateDownloaderCookie(
        { platform: 'bilibili', cookie },
        { silent: true },
      ).catch(() => null)
      if (result) setCookieValidation(result)
      toast.success('Bilibili Cookie 已保存')
      finish()
    } catch (error) {
      setError(`保存失败：${errText(error)}`)
    } finally {
      setCookieSaving(false)
    }
  }

  const startQrLogin = async () => {
    setError('')
    setQrStarting(true)
    try {
      const session = await startBilibiliQrCodeLogin('bilibili', { silent: true })
      if (!session.qrcode_key || !session.url) {
        setError(session.message || '生成二维码失败')
        return
      }
      setQrSession(session)
      setQrStatus(null)
      setCookieValidation(null)
      toast.success('Bilibili 登录二维码已生成')
    } catch (error) {
      setError(`生成二维码失败：${errText(error)}`)
    } finally {
      setQrStarting(false)
    }
  }

  const statusByModel = useMemo(
    () => new Map(modelStatuses.map(status => [status.model_size, status])),
    [modelStatuses],
  )
  const modelRows = useMemo(() => {
    const sizes = transcriberConfig?.whisper_model_sizes || fallbackTranscriberConfig.whisper_model_sizes
    return sizes.map(
      size =>
        statusByModel.get(size) ||
        ({
          model_size: size,
          downloaded: false,
          downloading: activeDownloads.includes(size),
          failed: false,
          error: null,
        } as ModelStatus),
    )
  }, [activeDownloads, statusByModel, transcriberConfig?.whisper_model_sizes])
  const selectedStatus = statusByModel.get(selectedModel)
  const selectedProgress = downloadProgress[selectedModel] || selectedStatus?.progress || 0

  const primaryBusy =
    (activeStep === 'backend' && pinging) ||
    (activeStep === 'provider' && providerSaving) ||
    (activeStep === 'transcriber' && transcriberSaving) ||
    (activeStep === 'cookie' && cookieSaving)

  const primaryLabel =
    activeStep === 'backend'
      ? '下一步'
      : activeStep === 'provider'
        ? '保存并下一步'
        : activeStep === 'transcriber'
          ? '保存并下一步'
          : '保存并完成'

  const primaryDisabled =
    activeStep === 'backend'
      ? !backendOk || pinging
      : activeStep === 'provider'
        ? providerSaving
        : activeStep === 'transcriber'
          ? transcriberSaving || !selectedModel
          : cookieSaving

  const runPrimaryAction = () => {
    if (activeStep === 'backend') nextStep()
    else if (activeStep === 'provider') saveProviderAndContinue()
    else if (activeStep === 'transcriber') saveTranscriberAndContinue()
    else saveCookieAndFinish()
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-blue-50 via-white to-pink-50 p-6 text-slate-900">
      <div className="flex h-[min(760px,calc(100vh-48px))] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-white/80 bg-white shadow-[0_24px_60px_rgba(37,99,235,0.16)]">
        <header className="shrink-0 border-b border-slate-100 px-7 py-5">
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-3">
              <img src={logo} alt="AI Video Notes" className="h-10 w-10 rounded-lg" />
              <div>
                <h1 className="text-xl font-bold tracking-normal">欢迎使用 AI Video Notes</h1>
                <p className="mt-1 text-xs text-slate-500">
                  几步配置后，就可以开始把视频转成笔记。
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={finish}
              className="h-9 rounded-lg border border-slate-200 px-3 text-xs font-medium text-slate-500 transition-colors hover:border-slate-300 hover:bg-slate-50 hover:text-slate-800"
            >
              稍后配置
            </button>
          </div>

          <StepProgress activeStep={activeStep} onStep={goToStep} stepIndex={stepIndex} />
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto px-7 py-6">
          {activeStep === 'backend' && (
            <BackendStep backendOk={backendOk} pinging={pinging} />
          )}
          {activeStep === 'provider' && (
            <ProviderStep
              presets={providerPresets}
              currentPreset={currentPreset}
              presetId={presetId}
              providerName={providerName}
              baseUrl={baseUrl}
              apiKey={apiKey}
              showApiKey={showApiKey}
              remoteModels={remoteModels}
              selectedModels={selectedModels}
              manualModelName={manualModelName}
              providerId={providerId}
              modelsLoading={modelsLoading}
              modelFetchAttempted={modelFetchAttempted}
              onPreset={applyPreset}
              onProviderName={setProviderName}
              onBaseUrl={setBaseUrl}
              onApiKey={setApiKey}
              onToggleApiKey={() => setShowApiKey(value => !value)}
              onFetchModels={fetchRemoteModelList}
              onToggleModel={toggleModel}
              onManualModelName={setManualModelName}
            />
          )}
          {activeStep === 'transcriber' && (
            <TranscriberStep
              loading={transcriberLoading}
              statusRefreshing={statusRefreshing}
              modelRows={modelRows}
              selectedModel={selectedModel}
              selectedDevice={selectedDevice}
              selectedStatus={selectedStatus}
              selectedProgress={selectedProgress}
              downloadProgress={downloadProgress}
              onRefresh={() => refreshModelStatus(true)}
              onSelectModel={setSelectedModel}
              onSelectDevice={setSelectedDevice}
              onDownload={startModelDownload}
            />
          )}
          {activeStep === 'cookie' && (
            <CookieStep
              cookie={cookie}
              cookieLoading={cookieLoading}
              cookieSaving={cookieSaving}
              cookieValidation={cookieValidation}
              qrSession={qrSession}
              qrStatus={qrStatus}
              qrStarting={qrStarting}
              qrPolling={qrPolling}
              onCookie={value => {
                setCookie(value)
                setCookieValidation(null)
              }}
              onValidate={validateCookieValue}
              onQr={startQrLogin}
              onCloseQr={() => {
                setQrSession(null)
                setQrStatus(null)
              }}
            />
          )}
          {error && (
            <div className="mt-5 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          )}
        </main>

        <footer className="shrink-0 border-t border-slate-100 bg-slate-50/80 px-7 py-4">
          <div className="flex items-center justify-between gap-4">
            <button
              type="button"
              onClick={prevStep}
              disabled={!canGoBack}
              className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ChevronLeft size={16} />
              上一步
            </button>

            <div className="flex items-center gap-2">
              {activeStep === 'backend' && backendOk !== true && (
                <button
                  type="button"
                  onClick={doPing}
                  disabled={pinging}
                  className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50"
                >
                  {pinging ? <Loader2 size={16} className="animate-spin" /> : <RefreshCcw size={16} />}
                  重新检测
                </button>
              )}
              {activeStep === 'cookie' && (
                <button
                  type="button"
                  onClick={finish}
                  className="h-10 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50"
                >
                  跳过
                </button>
              )}
              <button
                type="button"
                onClick={runPrimaryAction}
                disabled={primaryDisabled}
                className="inline-flex h-10 items-center gap-1.5 rounded-lg bg-blue-600 px-4 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {primaryBusy ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : activeStep === 'cookie' ? (
                  <Save size={16} />
                ) : (
                  <ChevronRight size={16} />
                )}
                {primaryLabel}
              </button>
            </div>
          </div>
        </footer>
      </div>
    </div>
  )
}

function StepProgress({
  activeStep,
  onStep,
  stepIndex,
}: {
  activeStep: StepId
  onStep: (stepId: StepId) => void
  stepIndex: number
}) {
  return (
    <div className="mt-5 grid gap-2 sm:grid-cols-4">
      {steps.map((step, index) => {
        const Icon = step.icon
        const active = activeStep === step.id
        const done = index < stepIndex
        return (
          <button
            key={step.id}
            type="button"
            onClick={() => onStep(step.id)}
            className={`group flex items-center gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors ${
              active
                ? 'border-blue-200 bg-blue-50 text-blue-700'
                : done
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-slate-200 bg-white text-slate-500 hover:border-slate-300 hover:bg-slate-50'
            }`}
          >
            <span
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                active
                  ? 'bg-blue-600 text-white'
                  : done
                    ? 'bg-emerald-600 text-white'
                    : 'bg-slate-100 text-slate-400 group-hover:bg-slate-200'
              }`}
            >
              {done ? <CheckCircle2 size={16} /> : <Icon size={16} />}
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold">{step.label}</span>
              <span className="mt-0.5 block text-[11px] text-slate-400">{index + 1}/4</span>
            </span>
          </button>
        )
      })}
    </div>
  )
}

function SectionHeading({
  detail,
  icon,
  title,
}: {
  detail: string
  icon: React.ReactNode
  title: string
}) {
  return (
    <div className="mb-5 flex items-start gap-3">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-blue-600">
        {icon}
      </div>
      <div>
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
        <p className="mt-1 text-sm leading-6 text-slate-500">{detail}</p>
      </div>
    </div>
  )
}

function BackendStep({
  backendOk,
  pinging,
}: {
  backendOk: boolean | null
  pinging: boolean
}) {
  return (
    <div>
      <SectionHeading
        icon={<Server size={18} />}
        title="第 1 步 · 后端连通性"
        detail="桌面端会自动启动内置后端；这里会请求 ready 接口确认当前进程可用。"
      />
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="text-sm font-semibold text-slate-800">后端状态</div>
            <div className="mt-1 text-xs text-slate-500">{getApiBaseURL()}/system/ready</div>
          </div>
          <StatusPill backendOk={backendOk} pinging={pinging} />
        </div>
      </div>
      {backendOk === false && (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
          暂时连不上后端。首次启动可能还在初始化，稍等后可以在底部重新检测。
        </div>
      )}
    </div>
  )
}

function StatusPill({ backendOk, pinging }: { backendOk: boolean | null; pinging: boolean }) {
  const className =
    backendOk === true
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
      : backendOk === false
        ? 'border-amber-200 bg-amber-50 text-amber-700'
        : 'border-slate-200 bg-white text-slate-500'
  return (
    <span className={`inline-flex w-fit items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${className}`}>
      {pinging ? (
        <Loader2 size={13} className="animate-spin" />
      ) : backendOk ? (
        <CheckCircle2 size={13} />
      ) : (
        <Server size={13} />
      )}
      {pinging ? '检测中' : backendOk === true ? '已就绪' : backendOk === false ? '等待后端' : '未检测'}
    </span>
  )
}

function ProviderStep({
  apiKey,
  baseUrl,
  currentPreset,
  manualModelName,
  modelFetchAttempted,
  modelsLoading,
  onApiKey,
  onBaseUrl,
  onFetchModels,
  onManualModelName,
  onPreset,
  onProviderName,
  onToggleApiKey,
  onToggleModel,
  presetId,
  presets,
  providerId,
  providerName,
  remoteModels,
  selectedModels,
  showApiKey,
}: {
  apiKey: string
  baseUrl: string
  currentPreset: ProviderPreset
  manualModelName: string
  modelFetchAttempted: boolean
  modelsLoading: boolean
  onApiKey: (value: string) => void
  onBaseUrl: (value: string) => void
  onFetchModels: () => void
  onManualModelName: (value: string) => void
  onPreset: (preset: ProviderPreset) => void
  onProviderName: (value: string) => void
  onToggleApiKey: () => void
  onToggleModel: (model: string) => void
  presetId: string
  presets: ProviderPreset[]
  providerId: string
  providerName: string
  remoteModels: RemoteModel[]
  selectedModels: string[]
  showApiKey: boolean
}) {
  return (
    <div>
      <SectionHeading
        icon={<KeyRound size={18} />}
        title="第 2 步 · 模型供应商"
        detail="选择模板后填写 API Key，再通过后端接口获取 Provider 真实模型列表。"
      />

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        {presets.map(preset => (
          <button
            key={preset.id}
            type="button"
            onClick={() => onPreset(preset)}
            className={`rounded-lg border p-3 text-left transition-colors ${
              presetId === preset.id
                ? 'border-blue-200 bg-blue-50 text-blue-700'
                : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50'
            }`}
          >
            <div className="text-sm font-semibold">{preset.label}</div>
            <div className="mt-1 line-clamp-2 text-[11px] leading-4 text-slate-500">
              {preset.description}
            </div>
          </button>
        ))}
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.25fr)]">
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="grid gap-3">
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-slate-500">
                Provider 名称
              </span>
              <input
                value={providerName}
                onChange={event => onProviderName(event.target.value)}
                className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
              />
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-slate-500">
                Base URL
              </span>
              <input
                value={baseUrl}
                onChange={event => onBaseUrl(event.target.value)}
                placeholder="https://api.example.com/v1"
                className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
              />
            </label>

            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-slate-500">
                API Key
              </span>
              <div className="relative">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  value={apiKey}
                  onChange={event => onApiKey(event.target.value)}
                  placeholder="sk-..."
                  className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 pr-10 text-sm text-slate-900 outline-none transition-colors focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
                />
                <button
                  type="button"
                  onClick={onToggleApiKey}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 transition-colors hover:text-slate-700"
                  aria-label={showApiKey ? '隐藏 API Key' : '显示 API Key'}
                >
                  {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </label>

            {providerId && (
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-700">
                Provider 已保存，继续获取模型会复用并更新该配置。
              </div>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-slate-800">模型列表</div>
              <div className="mt-1 text-xs text-slate-500">
                {currentPreset.label} / 已选 {selectedModels.length}
              </div>
            </div>
            <button
              type="button"
              onClick={onFetchModels}
              disabled={modelsLoading}
              className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-3 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100 disabled:opacity-50"
            >
              {modelsLoading ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
              获取模型
            </button>
          </div>

          <div className="min-h-[176px] max-h-[260px] overflow-y-auto rounded-lg border border-slate-200">
            {modelsLoading ? (
              <div className="flex h-[176px] items-center justify-center gap-2 text-sm text-slate-500">
                <Loader2 size={16} className="animate-spin" />
                正在请求 Provider 模型接口...
              </div>
            ) : remoteModels.length > 0 ? (
              remoteModels.map(model => {
                const selected = selectedModels.includes(model.id)
                return (
                  <button
                    key={model.id}
                    type="button"
                    onClick={() => onToggleModel(model.id)}
                    className="flex w-full items-center justify-between gap-3 border-b border-slate-100 px-3 py-2 text-left transition-colors last:border-b-0 hover:bg-slate-50"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium text-slate-800">
                        {model.displayName}
                      </span>
                      {model.displayName !== model.id && (
                        <span className="mt-0.5 block truncate text-[11px] text-slate-500">
                          {model.id}
                        </span>
                      )}
                    </span>
                    <span
                      className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] ${
                        selected
                          ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                          : 'border-slate-200 bg-slate-50 text-slate-500'
                      }`}
                    >
                      {selected ? '启用' : '未选'}
                    </span>
                  </button>
                )
              })
            ) : (
              <div className="flex h-[176px] flex-col items-center justify-center px-5 text-center">
                <div className="text-sm font-medium text-slate-700">
                  {modelFetchAttempted ? '接口没有返回模型' : '还没有获取模型'}
                </div>
                <div className="mt-1 max-w-sm text-xs leading-5 text-slate-500">
                  {modelFetchAttempted
                    ? '请检查 API Key 与 Base URL，或在下方手动填写一个模型名。'
                    : '填写 API Key 后点击“获取模型”，这里会显示后端从 Provider 查询到的真实列表。'}
                </div>
              </div>
            )}
          </div>

          <label className="mt-3 block">
            <span className="mb-1.5 block text-xs font-medium text-slate-500">
              手动模型名（接口不可用时使用）
            </span>
            <input
              value={manualModelName}
              onChange={event => onManualModelName(event.target.value)}
              placeholder="留空时只保存上方选中的模型"
              className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            />
          </label>
        </div>
      </div>
    </div>
  )
}

function TranscriberStep({
  downloadProgress,
  loading,
  modelRows,
  onDownload,
  onRefresh,
  onSelectDevice,
  onSelectModel,
  selectedDevice,
  selectedModel,
  selectedProgress,
  selectedStatus,
  statusRefreshing,
}: {
  downloadProgress: Record<string, number>
  loading: boolean
  modelRows: ModelStatus[]
  onDownload: (model: string) => void
  onRefresh: () => void
  onSelectDevice: (device: string) => void
  onSelectModel: (model: string) => void
  selectedDevice: string
  selectedModel: string
  selectedProgress: number
  selectedStatus?: ModelStatus
  statusRefreshing: boolean
}) {
  const selectedState = modelState(selectedStatus, selectedProgress)

  return (
    <div>
      <SectionHeading
        icon={<MessageSquareText size={18} />}
        title="第 3 步 · 本地转写模型"
        detail="选择 Whisper 模型尺寸，可直接下载本地缓存；后续视频转写会使用这里保存的模型。"
      />

      {loading ? (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 size={16} className="animate-spin" />
          加载转写配置...
        </div>
      ) : (
        <>
          <div className="mb-4 flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm font-semibold text-slate-900">
                  {selectedModel || '未选择'}
                </span>
                <span className={`rounded-full border px-2 py-0.5 text-[11px] ${selectedState.className}`}>
                  {selectedState.label}
                </span>
              </div>
              <div className="mt-1 text-xs text-slate-500">
                {modelRepoLabel(selectedStatus, selectedModel)}
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={onRefresh}
                disabled={statusRefreshing}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50"
              >
                {statusRefreshing ? <Loader2 size={15} className="animate-spin" /> : <RefreshCcw size={15} />}
                重新扫描
              </button>
              {selectedModel && !selectedStatus?.downloaded && !selectedStatus?.downloading && (
                <button
                  type="button"
                  onClick={() => onDownload(selectedModel)}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-3 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100"
                >
                  <Download size={15} />
                  下载当前模型
                </button>
              )}
            </div>
          </div>

          {(selectedStatus?.downloading || selectedProgress > 0) && (
            <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-blue-500 transition-all duration-500"
                style={{ width: `${Math.min(selectedProgress || 8, 100)}%` }}
              />
            </div>
          )}

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {modelRows.map(status => {
              const progress = downloadProgress[status.model_size] || status.progress || 0
              const state = modelState(status, progress)
              const selected = selectedModel === status.model_size
              return (
                <button
                  key={status.model_size}
                  type="button"
                  onClick={() => onSelectModel(status.model_size)}
                  className={`rounded-lg border p-3 text-left transition-colors ${
                    selected
                      ? 'border-blue-200 bg-blue-50'
                      : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm font-semibold text-slate-900">
                        {status.model_size}
                      </div>
                      <div className="mt-1 text-[11px] text-slate-500">
                        {modelSizeLabel(status, status.model_size)}
                      </div>
                    </div>
                    <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] ${state.className}`}>
                      {status.downloaded
                        ? '已缓存'
                        : status.downloading
                          ? '下载中'
                          : status.partial
                            ? '未完整'
                            : '未下载'}
                    </span>
                  </div>
                  <div className="mt-2 truncate text-[11px] text-slate-400">
                    {modelRepoLabel(status, status.model_size)}
                  </div>
                  {(status.downloading || progress > 0) && (
                    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-blue-500"
                        style={{ width: `${Math.min(progress || 8, 100)}%` }}
                      />
                    </div>
                  )}
                </button>
              )
            })}
          </div>

          <label className="mt-5 block max-w-[260px]">
            <span className="mb-1.5 block text-xs font-medium text-slate-500">转写设备</span>
            <select
              value={selectedDevice}
              onChange={event => onSelectDevice(event.target.value)}
              className="h-10 w-full rounded-lg border border-slate-200 bg-white px-3 text-sm text-slate-900 outline-none transition-colors focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            >
              <option value="auto">自动</option>
              <option value="cpu">CPU</option>
              <option value="cuda">CUDA</option>
            </select>
          </label>
        </>
      )}
    </div>
  )
}

function CookieStep({
  cookie,
  cookieLoading,
  cookieSaving,
  cookieValidation,
  onCloseQr,
  onCookie,
  onQr,
  onValidate,
  qrPolling,
  qrSession,
  qrStarting,
  qrStatus,
}: {
  cookie: string
  cookieLoading: boolean
  cookieSaving: boolean
  cookieValidation: DownloaderCookieValidation | null
  onCloseQr: () => void
  onCookie: (value: string) => void
  onQr: () => void
  onValidate: () => void
  qrPolling: boolean
  qrSession: BilibiliQrCodeSession | null
  qrStarting: boolean
  qrStatus: BilibiliQrCodePollResult | null
}) {
  return (
    <div>
      <SectionHeading
        icon={<ShieldCheck size={18} />}
        title="第 4 步 · Bilibili Cookie"
        detail="需要登录态的视频可以在这里完成授权；不配置也可以进入应用，后续仍可在设置页补充。"
      />

      {cookieLoading ? (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Loader2 size={16} className="animate-spin" />
          加载 Cookie...
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_240px]">
          <div className="space-y-3">
            <textarea
              value={cookie}
              onChange={event => onCookie(event.target.value)}
              placeholder="SESSDATA=..."
              rows={8}
              className="w-full resize-none rounded-lg border border-slate-200 bg-white px-3 py-3 text-sm text-slate-900 outline-none transition-colors focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={onValidate}
                disabled={cookieSaving || !cookie.trim()}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 text-sm font-medium text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50"
              >
                {cookieSaving ? <Loader2 size={15} className="animate-spin" /> : <RefreshCcw size={15} />}
                验证 Cookie
              </button>
            </div>

            {cookieValidation && (
              <div
                className={`flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-xs ${
                  cookieValidation.valid
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : 'border-amber-200 bg-amber-50 text-amber-700'
                }`}
              >
                {cookieValidation.valid ? <CheckCircle2 size={14} /> : <X size={14} />}
                <span>
                  {cookieValidation.message ||
                    (cookieValidation.valid ? '已登录' : '未登录')}
                </span>
                {cookieValidation.username && <span>用户：{cookieValidation.username}</span>}
                {cookieValidation.level != null && <span>等级：{cookieValidation.level}</span>}
              </div>
            )}
          </div>

          <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
            <button
              type="button"
              onClick={onQr}
              disabled={qrStarting}
              className="mb-3 inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-lg border border-blue-200 bg-blue-50 text-sm font-medium text-blue-700 transition-colors hover:bg-blue-100 disabled:opacity-50"
            >
              {qrStarting ? <Loader2 size={15} className="animate-spin" /> : <QrCode size={15} />}
              扫码填入
            </button>

            {qrSession ? (
              <div>
                <div className="mx-auto flex h-[180px] w-[180px] items-center justify-center rounded-lg bg-white p-2 shadow-sm">
                  <AntQRCode
                    value={qrSession.url}
                    size={158}
                    bordered={false}
                    color="#111111"
                    bgColor="#ffffff"
                  />
                </div>
                <div className="mt-3 flex items-center justify-between gap-2">
                  <span className="inline-flex min-w-0 items-center gap-1.5 truncate text-xs text-slate-500">
                    {qrPolling && <Loader2 size={13} className="animate-spin" />}
                    {qrStatus?.message || '等待扫码'}
                  </span>
                  <button
                    type="button"
                    onClick={onCloseQr}
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-800"
                    aria-label="关闭二维码"
                  >
                    <X size={13} />
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex h-[180px] items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white text-xs text-slate-400">
                可选授权
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
