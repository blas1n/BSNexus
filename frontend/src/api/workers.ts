import apiClient from './client'
import type { Worker, WorkerRegister } from '../types/worker'

export const workersApi = {
  list: () => apiClient.get<Worker[]>('/api/v1/workers').then(r => r.data),
  register: (data: WorkerRegister) => apiClient.post<Worker>('/api/v1/workers/register', data).then(r => r.data),
  heartbeat: (id: string) => apiClient.post(`/api/v1/workers/${id}/heartbeat`).then(r => r.data),
}
