import type { Task, TaskStatus } from '../../types/task'
import { tasksApi } from '../../api/tasks'
import { useBoardStore } from '../../stores/boardStore'

const allowedTransitions: Partial<Record<TaskStatus, { label: string; to: TaskStatus; color: string }[]>> = {
  rejected: [{ label: 'Retry', to: 'ready', color: 'bg-blue-600 hover:bg-blue-700' }],
  ready: [{ label: 'Queue', to: 'queued', color: 'bg-yellow-600 hover:bg-yellow-700' }],
  blocked: [{ label: 'Unblock', to: 'ready', color: 'bg-blue-600 hover:bg-blue-700' }],
}

const statusBadgeColors: Record<string, string> = {
  waiting: 'bg-gray-100 text-gray-700',
  ready: 'bg-blue-100 text-blue-700',
  queued: 'bg-yellow-100 text-yellow-700',
  in_progress: 'bg-orange-100 text-orange-700',
  review: 'bg-purple-100 text-purple-700',
  done: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  blocked: 'bg-red-50 text-red-600',
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="w-full max-w-lg max-h-[80vh] overflow-y-auto rounded-lg bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">{task.title}</h2>
            <div className="mt-1 flex items-center gap-2">
              <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusBadgeColors[task.status]}`}>
                {task.status}
              </span>
              <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">
                {task.priority}
              </span>
              <span className="text-xs text-gray-400">v{task.version}</span>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">
            &times;
          </button>
        </div>

        {/* Description */}
        {task.description && (
          <div className="mb-4">
            <h3 className="text-sm font-medium text-gray-700 mb-1">Description</h3>
            <p className="text-sm text-gray-600 whitespace-pre-wrap">{task.description}</p>
          </div>
        )}

        {/* Details grid */}
        <div className="mb-4 grid grid-cols-2 gap-3 text-sm">
          <div>
            <span className="font-medium text-gray-700">Phase ID</span>
            <p className="text-gray-500 truncate">{task.phase_id}</p>
          </div>
          {task.worker_id && (
            <div>
              <span className="font-medium text-gray-700">Worker</span>
              <p className="text-gray-500 truncate">{task.worker_id}</p>
            </div>
          )}
          {task.reviewer_id && (
            <div>
              <span className="font-medium text-gray-700">Reviewer</span>
              <p className="text-gray-500 truncate">{task.reviewer_id}</p>
            </div>
          )}
          {task.branch_name && (
            <div>
              <span className="font-medium text-gray-700">Branch</span>
              <p className="text-gray-500 truncate">{task.branch_name}</p>
            </div>
          )}
          <div>
            <span className="font-medium text-gray-700">Created</span>
            <p className="text-gray-500">{new Date(task.created_at).toLocaleString()}</p>
          </div>
          {task.started_at && (
            <div>
              <span className="font-medium text-gray-700">Started</span>
              <p className="text-gray-500">{new Date(task.started_at).toLocaleString()}</p>
            </div>
          )}
          {task.completed_at && (
            <div>
              <span className="font-medium text-gray-700">Completed</span>
              <p className="text-gray-500">{new Date(task.completed_at).toLocaleString()}</p>
            </div>
          )}
        </div>

        {/* Dependencies */}
        {task.depends_on.length > 0 && (
          <div className="mb-4">
            <h3 className="text-sm font-medium text-gray-700 mb-1">Dependencies ({task.depends_on.length})</h3>
            <div className="flex flex-wrap gap-1">
              {task.depends_on.map((depId) => (
                <span key={depId} className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600 font-mono">
                  {depId.slice(0, 8)}...
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Error message */}
        {task.error_message && (
          <div className="mb-4 rounded-md bg-red-50 p-3">
            <h3 className="text-sm font-medium text-red-800 mb-1">Error</h3>
            <p className="text-sm text-red-700 whitespace-pre-wrap">{task.error_message}</p>
          </div>
        )}

        {/* QA Result */}
        {task.qa_result && (
          <div className="mb-4 rounded-md bg-purple-50 p-3">
            <h3 className="text-sm font-medium text-purple-800 mb-1">QA Result</h3>
            <pre className="text-xs text-purple-700 whitespace-pre-wrap">{JSON.stringify(task.qa_result, null, 2)}</pre>
          </div>
        )}

        {/* Transition buttons */}
        {transitions.length > 0 && (
          <div className="flex gap-2 pt-4 border-t border-gray-200">
            {transitions.map((t) => (
              <button
                key={t.to}
                onClick={() => handleTransition(t.to)}
                className={`rounded-md px-4 py-2 text-sm font-medium text-white ${t.color}`}
              >
                {t.label} &rarr; {t.to}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
