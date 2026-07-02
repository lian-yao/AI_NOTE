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
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      suppressNotFoundToast: true,
    })
  } catch (error) {
    if (isNotFoundError(error)) {
      throw new Error('本地视频上传接口暂未实现，请先使用视频链接生成笔记')
    }
    throw error
  }
}
