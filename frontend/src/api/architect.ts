import apiClient from './client'
import type { DesignSession, CreateSessionRequest, DesignMessageResponse, FinalizeRequest } from '../types/architect'
import type { Project } from '../types/project'
import type { Task } from '../types/task'

export interface RedesignRequest {
  action: 'modify' | 'delete' | 'split'
  title?: string
  description?: string
  worker_prompt?: string
  qa_prompt?: string
  split_tasks?: Array<Record<string, unknown>>
}

export interface StreamCallbacks {
  onChunk: (text: string) => void
  onDone: (fullText: string) => void
  onFinalizeReady: (designContext: string) => void
  onError: (message: string) => void
}

export const architectApi = {
  listSessions: (status?: string) => apiClient.get<DesignSession[]>('/api/v1/architect/sessions', { params: status ? { status } : undefined }).then(r => r.data),
  createSession: (data: CreateSessionRequest) => apiClient.post<DesignSession>('/api/v1/architect/sessions', data).then(r => r.data),
  getSession: (id: string) => apiClient.get<DesignSession>(`/api/v1/architect/sessions/${id}`).then(r => r.data),
  sendMessage: (sessionId: string, content: string) => apiClient.post<DesignMessageResponse>(`/api/v1/architect/sessions/${sessionId}/message`, { content }).then(r => r.data),
  finalize: (sessionId: string, data: FinalizeRequest) => apiClient.post<Project>(`/api/v1/architect/sessions/${sessionId}/finalize`, data).then(r => r.data),
  deleteSession: (id: string) => apiClient.delete(`/api/v1/architect/sessions/${id}`).then(r => r.data),
  batchDeleteSessions: (ids: string[]) => apiClient.post<{ deleted: number }>('/api/v1/architect/sessions/batch-delete', { ids }).then(r => r.data),
  redesignTask: (taskId: string, data: RedesignRequest) => apiClient.post<Task>(`/api/v1/architect/redesign/${taskId}`, data).then(r => r.data),

  streamMessage: (sessionId: string, content: string, callbacks: StreamCallbacks): AbortController => {
    const controller = new AbortController()
    const baseUrl = import.meta.env.VITE_API_URL || ''
    const url = `${baseUrl}/api/v1/architect/sessions/${sessionId}/message/stream`

    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) {
          const text = await response.text()
          callbacks.onError(`HTTP ${response.status}: ${text}`)
          return
        }
        const reader = response.body?.getReader()
        if (!reader) {
          callbacks.onError('No response body')
          return
        }
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          let currentEvent = ''
          for (const line of lines) {
            if (line.startsWith('event:')) {
              currentEvent = line.slice(6).trim()
            } else if (line.startsWith('data:')) {
              const data = line.slice(5).trim()
              switch (currentEvent) {
                case 'chunk':
                  callbacks.onChunk(data)
                  break
                case 'done':
                  callbacks.onDone(data)
                  break
                case 'finalize_ready':
                  callbacks.onFinalizeReady(data)
                  break
                case 'error':
                  callbacks.onError(data)
                  break
              }
              currentEvent = ''
            }
          }
        }
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          callbacks.onError(err.message || 'Stream failed')
        }
      })

    return controller
  },
}
