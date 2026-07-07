import { create } from 'zustand'
import { IProvider } from '@/types'
import {
  addProvider,
  getProviderById,
  getProviderList,
  updateProviderById,
} from '@/services/model.ts'

interface ProviderStore {
  provider: IProvider[]
  setProvider: (provider: IProvider) => void
  setAllProviders: (providers: IProvider[]) => void
  getProviderById: (id: string) => IProvider | undefined
  getProviderList: () => IProvider[]
  fetchProviderList: (opts?: { silent?: boolean }) => Promise<boolean>
  loadProviderById: (id: string, opts?: { silent?: boolean }) => Promise<IProvider | void>
  addNewProvider: (provider: IProvider) => Promise<string | void>
  updateProvider: (provider: IProvider) => Promise<void>
}

export const useProviderStore = create<ProviderStore>((set, get) => ({
  provider: [],

  // 添加或更新一个 provider
  setProvider: newProvider =>
    set(state => {
      const exists = state.provider.find(p => p.id === newProvider.id)
      if (exists) {
        return {
          provider: state.provider.map(p => (p.id === newProvider.id ? newProvider : p)),
        }
      } else {
        return { provider: [...state.provider, newProvider] }
      }
    }),

  // 设置整个 provider 列表
  setAllProviders: providers => set({ provider: providers }),
  loadProviderById: async (id: string, opts) => {
    const res = await getProviderById(id, opts)

      const item = res
      return {
        id: item.id,
        name: item.name,
        logo: item.logo,
        apiKey: item.api_key,
        baseUrl: item.base_url,
        type: item.type,
        enabled: item.enabled,
        has_api_key: item.has_api_key,
      }

  },
  addNewProvider: async (provider: IProvider) => {
    const payload = {
      ...provider,
      api_key: provider.apiKey,
      base_url: provider.baseUrl,
    }
    try {
      const id = await addProvider(payload)
      await get().fetchProviderList()
      return id
    } catch (error) {
      console.error('Error fetching provider:', error)
    }
  },
  // 按 id 获取单个 provider
  getProviderById: id => get().provider.find(p => p.id === id),
  updateProvider: async (provider: IProvider) => {
    try {
      const existing = get().provider.find(p => p.id === provider.id)
      const merged = { ...existing, ...provider }

      const data = {
        ...merged,
        api_key: merged.apiKey,
        base_url: merged.baseUrl,
      }
      // 拦截器已解包：成功时直接返回 data 部分
      await updateProviderById(data)
      await get().fetchProviderList()
    } catch (error) {
      console.error('Error updating provider:', error)
    }
  },
  getProviderList: () => get().provider,
  fetchProviderList: async (opts) => {
    try {
      const res  = await getProviderList(opts)

        set({
          provider: res.map(
            (item: {
              id: string
              name: string
              logo: string
              api_key: string
              has_api_key?: boolean
              base_url: string
              type: string
              enabled: number
            }) => {
              return {
                id: item.id,
                name: item.name,
                logo: item.logo,
                apiKey: item.api_key,
                baseUrl: item.base_url,
                type: item.type,
                enabled: item.enabled,
                has_api_key: item.has_api_key,
              }
            }
          ),
        })
        return true
    } catch (error) {
      console.error('Error fetching provider list:', error)
      return false
    }
  },
}))
