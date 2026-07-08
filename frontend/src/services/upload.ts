import request, { isNotFoundError } from '@/utils/request'

export interface UploadResponse {
  file_id: string
  filename: string
  size_bytes: number
  url: string
}

export const uploadFile = async (formData: FormData): Promise<UploadResponse> => {
  try {
    return await request.post<unknown, UploadResponse>('/uploads/videos', formData, {
      // 不手动设置 Content-Type，让浏览器自动添加 multipart/form-data 的 boundary
      suppressNotFoundToast: true,
      timeout: 300000,
    })
  } catch (error) {
    if (isNotFoundError(error)) {
      throw new Error('本地视频上传接口暂未实现，请先使用视频链接生成笔记')
    }
    throw error
  }
}
