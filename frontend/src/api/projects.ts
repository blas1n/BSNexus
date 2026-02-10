import apiClient from './client'
import type { Project, ProjectCreate, ProjectUpdate } from '../types/project'

export const projectsApi = {
  list: () => apiClient.get<Project[]>('/api/v1/projects').then(r => r.data),
  get: (id: string) => apiClient.get<Project>(`/api/v1/projects/${id}`).then(r => r.data),
  create: (data: ProjectCreate) => apiClient.post<Project>('/api/v1/projects', data).then(r => r.data),
  update: (id: string, data: ProjectUpdate) => apiClient.patch<Project>(`/api/v1/projects/${id}`, data).then(r => r.data),
}
