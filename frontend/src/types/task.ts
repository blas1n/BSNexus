export type TaskStatus = 'waiting' | 'ready' | 'queued' | 'in_progress' | 'review' | 'done' | 'rejected' | 'blocked'
export type TaskPriority = 'low' | 'medium' | 'high' | 'critical'

export interface Task {
  id: string
  project_id: string
  phase_id: string
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  worker_prompt: Record<string, unknown> | null
  qa_prompt: Record<string, unknown> | null
  branch_name: string | null
  commit_hash: string | null
  worker_id: string | null
  reviewer_id: string | null
  qa_result: Record<string, unknown> | null
  output_path: string | null
  error_message: string | null
  version: number
  created_at: string
  updated_at: string
  started_at: string | null
  completed_at: string | null
  depends_on: string[]
}

export interface TaskCreate {
  project_id: string
  phase_id: string
  title: string
  description: string
  priority: TaskPriority
  depends_on: string[]
  worker_prompt: string
  qa_prompt: string
}

export interface TaskUpdate {
  title?: string
  description?: string
  priority?: TaskPriority
  expected_version?: number
}

export interface TaskTransition {
  new_status: TaskStatus
  reason?: string
  actor?: string
  expected_version?: number
}

export interface TransitionResponse {
  task_id: string
  status: TaskStatus
  previous_status: TaskStatus
  transition: Record<string, unknown>
}

export interface BoardColumn {
  tasks: Task[]
}

export interface BoardResponse {
  project_id: string
  columns: Record<string, BoardColumn>
  stats: Record<string, number>
  workers: Record<string, number>
}
