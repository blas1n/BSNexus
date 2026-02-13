import apiClient from './client'
import type { Worker, WorkerRegister, RegistrationToken, RegistrationTokenCreate } from '../types/worker'

export const workersApi = {
  list: () => apiClient.get<Worker[]>('/api/v1/workers').then(r => r.data),
  register: (data: WorkerRegister) => apiClient.post<Worker>('/api/v1/workers/register', data).then(r => r.data),
  heartbeat: (id: string) => apiClient.post(`/api/v1/workers/${id}/heartbeat`).then(r => r.data),
}

export const registrationTokensApi = {
  create: (data?: RegistrationTokenCreate) =>
    apiClient.post<RegistrationToken>('/api/v1/registration-tokens', data ?? {}).then(r => r.data),
  list: () => apiClient.get<RegistrationToken[]>('/api/v1/registration-tokens').then(r => r.data),
  revoke: (tokenId: string) =>
    apiClient.delete(`/api/v1/registration-tokens/${tokenId}`).then(r => r.data),
}
