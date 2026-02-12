import type { Task, TaskStatus } from '../../types/task'
import { tasksApi } from '../../api/tasks'
import { useBoardStore } from '../../stores/boardStore'
import { Modal, Badge, Button } from '../common'

const allowedTransitions: Partial<Record<TaskStatus, { label: string; to: TaskStatus }[]>> = {
  rejected: [{ label: 'Retry', to: 'ready' }],
  ready: [{ label: 'Queue', to: 'queued' }],
  blocked: [{ label: 'Unblock', to: 'ready' }],
}

interface Props {
  task: Task
  onClose: () => void
}

export default function TaskDetail({ task, onClose }: Props) {
  const { moveTask, updateTask } = useBoardStore()
  const transitions = allowedTransitions[task.status] || []

  const handleTransition = async (to: TaskStatus) => {
    try {
      const result = await tasksApi.transition(task.id, {
        new_status: to,
        actor: 'user',
        expected_version: task.version,
      })
      moveTask(task.id, task.status, to)
      updateTask({ ...task, status: to, version: result.transition ? task.version + 1 : task.version })
    } catch {
      // Error handling
    }
  }

  const footer = transitions.length > 0 ? (
    <>
      {transitions.map((t) => (
        <Button
          key={t.to}
          onClick={() => handleTransition(t.to)}
          variant="primary"
          size="md"
        >
          {t.label} &rarr; {t.to}
        </Button>
      ))}
    </>
  ) : undefined

  return (
    <Modal open={true} onClose={onClose} title={task.title} footer={footer} width={520}>
      {/* Status and priority */}
      <div className="mb-4 flex items-center gap-2">
        <Badge color={task.status} label={task.status} />
        <Badge color={task.priority} label={task.priority} />
        <span className="text-xs text-text-tertiary">v{task.version}</span>
      </div>

      {/* Description */}
      {task.description && (
        <div className="mb-4">
          <h3 className="text-sm font-medium text-text-secondary mb-1">Description</h3>
          <p className="text-sm text-text-primary whitespace-pre-wrap">{task.description}</p>
        </div>
      )}

      {/* Details grid */}
      <div className="mb-4 grid grid-cols-2 gap-3 text-sm">
        <div>
          <span className="text-text-secondary">Phase ID</span>
          <p className="text-text-primary truncate">{task.phase_id}</p>
        </div>
        {task.worker_id && (
          <div>
            <span className="text-text-secondary">Worker</span>
            <p className="text-text-primary truncate">{task.worker_id}</p>
          </div>
        )}
        {task.reviewer_id && (
          <div>
            <span className="text-text-secondary">Reviewer</span>
            <p className="text-text-primary truncate">{task.reviewer_id}</p>
          </div>
        )}
        {task.branch_name && (
          <div>
            <span className="text-text-secondary">Branch</span>
            <p className="text-text-primary truncate">{task.branch_name}</p>
          </div>
        )}
        <div>
          <span className="text-text-secondary">Created</span>
          <p className="text-text-primary">{new Date(task.created_at).toLocaleString()}</p>
        </div>
        {task.started_at && (
          <div>
            <span className="text-text-secondary">Started</span>
            <p className="text-text-primary">{new Date(task.started_at).toLocaleString()}</p>
          </div>
        )}
        {task.completed_at && (
          <div>
            <span className="text-text-secondary">Completed</span>
            <p className="text-text-primary">{new Date(task.completed_at).toLocaleString()}</p>
          </div>
        )}
      </div>

      {/* Dependencies */}
      {task.depends_on.length > 0 && (
        <div className="mb-4">
          <h3 className="text-sm font-medium text-text-secondary mb-1">Dependencies ({task.depends_on.length})</h3>
          <div className="flex flex-wrap gap-1">
            {task.depends_on.map((depId) => (
              <span key={depId} className="rounded bg-bg-elevated px-2 py-0.5 text-xs text-text-secondary font-mono">
                {depId.slice(0, 8)}...
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Error message */}
      {task.error_message && (
        <div
          className="mb-4 rounded-md border p-3"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--status-rejected) 10%, transparent)',
            borderColor: 'var(--status-rejected)',
          }}
        >
          <h3
            className="text-sm font-medium mb-1"
            style={{ color: 'var(--status-rejected)' }}
          >
            Error
          </h3>
          <p className="text-sm text-text-primary whitespace-pre-wrap">{task.error_message}</p>
        </div>
      )}

      {/* QA Result */}
      {task.qa_result && (
        <div
          className="mb-4 rounded-md border p-3"
          style={{
            backgroundColor: 'color-mix(in srgb, var(--status-review) 10%, transparent)',
            borderColor: 'var(--status-review)',
          }}
        >
          <h3
            className="text-sm font-medium mb-1"
            style={{ color: 'var(--status-review)' }}
          >
            QA Result
          </h3>
          <pre className="text-xs text-text-primary whitespace-pre-wrap">{JSON.stringify(task.qa_result, null, 2)}</pre>
        </div>
      )}
    </Modal>
  )
}
