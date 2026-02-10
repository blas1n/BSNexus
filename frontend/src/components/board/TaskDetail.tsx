import type { Task } from '../../types/task'

interface Props {
  task: Task
  onClose: () => void
}

export default function TaskDetail({ task, onClose }: Props) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">{task.title}</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">&times;</button>
        </div>
        <div className="space-y-3 text-sm text-gray-600">
          <p><span className="font-medium">Status:</span> {task.status}</p>
          <p><span className="font-medium">Priority:</span> {task.priority}</p>
          {task.description && <p><span className="font-medium">Description:</span> {task.description}</p>}
          {task.error_message && <p className="text-red-600"><span className="font-medium">Error:</span> {task.error_message}</p>}
        </div>
      </div>
    </div>
  )
}
