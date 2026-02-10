import apiClient from './client'
import type { BoardResponse } from '../types/task'

export const boardApi = {
  get: (projectId: string) => apiClient.get<BoardResponse>(`/api/v1/board/${projectId}`).then(r => r.data),
}
