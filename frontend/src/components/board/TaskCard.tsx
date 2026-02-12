import type { Task } from '../../types/task'

const priorityColors: Record<string, string> = {
  low: 'bg-gray-100 text-gray-700',
  medium: 'bg-blue-100 text-blue-700',
  high: 'bg-orange-100 text-orange-700',
  critical: 'bg-red-100 text-red-700',
}

const priorityDots: Record<string, string> = {
  low: 'bg-gray-400',
  medium: 'bg-blue-400',
  high: 'bg-orange-400',
  critical: 'bg-red-400',
}

interface Props {
  task: Task
  onClick?: () => void
}

export default function TaskCard({ task, onClick }: Props) {
  return (
    <div
      onClick={onClick}
      className="cursor-pointer rounded-lg border border-border bg-bg-card p-3 shadow-sm hover:shadow-md transition-all duration-200"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h4 className="text-sm font-medium text-text-primary leading-snug">{task.title}</h4>
        <span
          className={`inline-block w-2 h-2 rounded-full flex-shrink-0 mt-1.5 ${priorityDots[task.priority]}`}
          title={task.priority}
        />
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <span className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${priorityColors[task.priority]}`}>
          {task.priority}
        </span>
        {task.depends_on.length > 0 && (
          <span
            className="inline-flex items-center gap-0.5 text-xs text-text-tertiary"
            title={`Depends on ${task.depends_on.length} task(s)`}
          >
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"
              />
            </svg>
            {task.depends_on.length}
          </span>
        )}
        {task.worker_id && (
          <span className="inline-flex items-center gap-0.5 text-xs text-text-tertiary" title="Worker assigned">
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
              />
            </svg>
          </span>
        )}
      </div>
    </div>
  )
}
