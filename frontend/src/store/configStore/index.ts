import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type CacheDirectoryKey = 'downloads' | 'transcripts' | 'covers' | 'temp'

export interface StoragePathConfig {
  knowledgeBasePath: string
  cacheRootPath: string
  cacheDirectories: Record<CacheDirectoryKey, string>
  lastCacheClearedAt: string | null
}

export function createDefaultStoragePathConfig(): StoragePathConfig {
  return {
    knowledgeBasePath: './data/knowledge',
    cacheRootPath: './data/cache',
    cacheDirectories: {
      downloads: './data/cache/downloads',
      transcripts: './data/cache/transcripts',
      covers: './data/cache/covers',
      temp: './data/cache/temp',
    },
    lastCacheClearedAt: null,
  }
}

interface SystemState {
  showFeatureHint: boolean // ✅ 是否显示功能提示
  setShowFeatureHint: (value: boolean) => void

  // 后续如果有其他全局状态，可以继续加
  sidebarCollapsed: boolean // ✅ 侧边栏是否收起
  setSidebarCollapsed: (value: boolean) => void

  storagePathConfig: StoragePathConfig
  setStoragePathConfig: (value: StoragePathConfig) => void
  resetStoragePathConfig: () => void
  markCacheClearedAt: (value: string) => void
}
// 暂不启用
export const useSystemStore = create<SystemState>()(
  persist(
    set => ({
      showFeatureHint: true,
      setShowFeatureHint: value => set({ showFeatureHint: value }),

      sidebarCollapsed: false,
      setSidebarCollapsed: value => set({ sidebarCollapsed: value }),

      storagePathConfig: createDefaultStoragePathConfig(),
      setStoragePathConfig: value => set({ storagePathConfig: value }),
      resetStoragePathConfig: () => set({ storagePathConfig: createDefaultStoragePathConfig() }),
      markCacheClearedAt: value =>
        set(state => ({
          storagePathConfig: {
            ...state.storagePathConfig,
            lastCacheClearedAt: value,
          },
        })),
    }),
    {
      name: 'system-store', // 本地存储的 key
    }
  )
)
