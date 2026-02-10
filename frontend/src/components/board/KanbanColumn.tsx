import type { Task } from '../../types/task'
import TaskCard from './TaskCard'

interface Props {
  title: string
  tasks: Task[]
  onTaskClick?: (task: Task) => void
}

export default function KanbanColumn({ title, tasks, onTaskClick }: Props) {
  return (
    <div className="flex-shrink-0 w-72">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">{title}</h3>
        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{tasks.length}</span>
      </div>
      <div className="space-y-2">
        {tasks.map((task) => (
          <TaskCard key={task.id} task={task} onClick={() => onTaskClick?.(task)} />
        ))}
      </div>
    </div>
  )
}
