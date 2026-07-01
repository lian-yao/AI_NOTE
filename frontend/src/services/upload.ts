import request from '@/utils/request' // 你项目里封装好的axios或者fetch

export interface UploadResponse {
  url: string
}

export const uploadFile = (formData: FormData): Promise<UploadResponse> => {
  return request.post<unknown, UploadResponse>('/upload', formData, {
    headers: {
      'Content-Type': 'multipart/form-data',
    },
  })
}
