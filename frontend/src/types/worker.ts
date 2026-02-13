export type WorkerStatus = 'idle' | 'busy' | 'offline'

export interface Worker {
  id: string
  name: string
  platform: string
  capabilities: Record<string, unknown> | null
  status: WorkerStatus
  current_task_id: string | null
  executor_type: string
  registered_at: string
  last_heartbeat: string | null
}

export interface WorkerRegister {
  name?: string
  platform: string
  capabilities?: Record<string, unknown>
  executor_type?: string
}

export interface WorkerHeartbeatResponse {
  status: WorkerStatus
  pending_tasks: number
}

export interface RegistrationToken {
  id: string
  token: string
  name: string
  created_at: string
  expires_at: string | null
  revoked: boolean
  server_url?: string
  redis_url?: string
}

export interface RegistrationTokenCreate {
  name?: string
}
