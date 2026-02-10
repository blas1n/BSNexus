import apiClient from './client'
import type { DesignSession, CreateSessionRequest, DesignMessageResponse, FinalizeRequest } from '../types/architect'
import type { Project } from '../types/project'

export const architectApi = {
  createSession: (data: CreateSessionRequest) => apiClient.post<DesignSession>('/api/v1/architect/sessions', data).then(r => r.data),
  getSession: (id: string) => apiClient.get<DesignSession>(`/api/v1/architect/sessions/${id}`).then(r => r.data),
  sendMessage: (sessionId: string, content: string) => apiClient.post<DesignMessageResponse>(`/api/v1/architect/sessions/${sessionId}/message`, { content }).then(r => r.data),
  finalize: (sessionId: string, data: FinalizeRequest) => apiClient.post<Project>(`/api/v1/architect/sessions/${sessionId}/finalize`, data).then(r => r.data),
}
