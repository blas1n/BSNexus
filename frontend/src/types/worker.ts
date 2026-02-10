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
