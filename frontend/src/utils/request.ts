import axios, { AxiosInstance, AxiosResponse } from 'axios'
import toast from 'react-hot-toast'
import { getApiBaseURL } from '@/utils/api'

export interface IResponse<T = unknown> {
  code: number
  message?: string
  msg?: string
  detail?: string
  status?: number
  statusCode?: number
  data: T
}

declare module 'axios' {
  export interface AxiosRequestConfig {
    suppressToast?: boolean
    suppressNotFoundToast?: boolean
  }
}

function responseMessage(res: Partial<IResponse> | undefined, fallback: string): string {
  if (!res) return fallback
  return res.message || res.msg || res.detail || fallback
}

export function isNotFoundError(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false

  const err = error as Partial<IResponse> & { status?: number; statusCode?: number }
  return (
    err.status === 404 ||
    err.statusCode === 404 ||
    err.detail === 'Not Found' ||
    err.message === 'Not Found'
  )
}

const request: AxiosInstance = axios.create({
  baseURL: getApiBaseURL(),
  timeout: 10000,
})

request.interceptors.response.use(
  (response: AxiosResponse<IResponse>): unknown => {
    const res = response.data

    if (!res || typeof res.code !== 'number') {
      return res
    }

    if (res.code === 0) {
      return res.data
    }

    if (!response.config?.suppressToast) {
      toast.error(responseMessage(res, '操作失败，请稍后再试'))
    }
    return Promise.reject(res)
  },
  error => {
    const status = error?.response?.status
    const suppressNotFoundToast = status === 404 && error?.config?.suppressNotFoundToast === true
    const suppress = error?.config?.suppressToast === true || suppressNotFoundToast
    const res = error?.response?.data as Partial<IResponse> | undefined

    if (res) {
      const apiError = {
        ...res,
        status,
        statusCode: status,
      }
      if (!suppress) toast.error(responseMessage(apiError, '服务器错误，请稍后再试'))
      return Promise.reject(apiError)
    }

    if (!suppress) toast.error('请求失败，请检查网络连接或稍后再试')
    return Promise.reject({
      code: -1,
      message: '请求失败，请检查网络连接',
      data: null,
    } as IResponse)
  }
)

export default request
