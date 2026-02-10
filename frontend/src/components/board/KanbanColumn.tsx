import type { Task } from '../../types/task'
import TaskCard from './TaskCard'

const columnColors: Record<string, { bg: string; border: string; text: string }> = {
  waiting: { bg: 'bg-gray-50', border: 'border-gray-300', text: 'text-gray-700' },
  ready: { bg: 'bg-blue-50', border: 'border-blue-300', text: 'text-blue-700' },
  queued: { bg: 'bg-yellow-50', border: 'border-yellow-300', text: 'text-yellow-700' },
  in_progress: { bg: 'bg-orange-50', border: 'border-orange-300', text: 'text-orange-700' },
  review: { bg: 'bg-purple-50', border: 'border-purple-300', text: 'text-purple-700' },
  done: { bg: 'bg-green-50', border: 'border-green-300', text: 'text-green-700' },
  rejected: { bg: 'bg-red-50', border: 'border-red-300', text: 'text-red-700' },
  blocked: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-600' },
}

interface Props {
  title: string
  status: string
  tasks: Task[]
  onTaskClick?: (task: Task) => void
}

export default function KanbanColumn({ title, status, tasks, onTaskClick }: Props) {
  const colors = columnColors[status] || columnColors.waiting

  return (
    <div className="flex-shrink-0 w-72">
      <div
        className={`mb-3 flex items-center justify-between rounded-t-lg border-t-2 ${colors.border} px-3 py-2 ${colors.bg}`}
      >
        <h3 className={`text-sm font-semibold ${colors.text}`}>{title}</h3>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colors.text} ${colors.bg}`}>
          {tasks.length}
        </span>
      </div>
      <div className="space-y-2 max-h-[calc(100vh-16rem)] overflow-y-auto pr-1">
        {tasks.map((task) => (
          <TaskCard key={task.id} task={task} onClick={() => onTaskClick?.(task)} />
        ))}
        {tasks.length === 0 && (
          <div className="rounded-lg border border-dashed border-gray-200 p-4 text-center text-xs text-gray-400">
            No tasks
          </div>
        )}
      </div>
    </div>
  )
}
