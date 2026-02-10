import apiClient from './client'
import type { AddTaskRequest, AddTaskResponse } from '../types/architect'

export const pmApi = {
  addTask: (projectId: string, data: AddTaskRequest) => apiClient.post<AddTaskResponse>(`/api/v1/pm/${projectId}/tasks`, data).then(r => r.data),
}
