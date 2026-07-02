export interface IProvider {
  id: string
  name: string
  logo: string
  type: string
  apiKey: string
  baseUrl: string
  enabled: number
  api_key?: string
  base_url?: string
  has_api_key?: boolean
}
export interface IResponse<T> {
  code: number
  data:T
  message: string
  msg?: string
  detail?: string
}
