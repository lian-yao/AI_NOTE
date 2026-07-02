import request from '@/utils/request'

export interface UploadResponse {
  file_id: string
  filename: string
  size_bytes: number
  url: string
}

export const uploadFile = (formData: FormData): Promise<UploadResponse> => {
  return request.post<unknown, UploadResponse>('/uploads/videos', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
}
