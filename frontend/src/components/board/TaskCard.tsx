import type { Task } from '../../types/task'

const priorityColors: Record<string, string> = {
  low: 'bg-gray-100 text-gray-700',
  medium: 'bg-blue-100 text-blue-700',
  high: 'bg-orange-100 text-orange-700',
  critical: 'bg-red-100 text-red-700',
}

interface Props {
  task: Task
  onClick?: () => void
}

export default function TaskCard({ task, onClick }: Props) {
  return (
    <div
      onClick={onClick}
      className="cursor-pointer rounded-lg border border-gray-200 bg-white p-3 shadow-sm hover:shadow-md transition-shadow"
    >
      <h4 className="text-sm font-medium text-gray-900 mb-1">{task.title}</h4>
      <div className="flex items-center gap-2">
        <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${priorityColors[task.priority]}`}>
          {task.priority}
        </span>
      </div>
    </div>
  )
}
