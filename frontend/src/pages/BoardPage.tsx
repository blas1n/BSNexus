import { useParams } from 'react-router-dom'
import { useBoard } from '../hooks/useBoard'
import { useBoardStore } from '../stores/boardStore'
import KanbanBoard from '../components/board/KanbanBoard'
import TaskDetail from '../components/board/TaskDetail'
import type { Task } from '../types/task'

export default function BoardPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { data: board, isLoading } = useBoard(projectId!)
  const { selectedTask, setSelectedTask } = useBoardStore()

  if (isLoading) return <div className="text-gray-500">Loading board...</div>
  if (!board) return <div className="text-gray-500">Board not found</div>

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Kanban Board</h2>
      <KanbanBoard board={board} onTaskClick={(task: Task) => setSelectedTask(task)} />
      {selectedTask && <TaskDetail task={selectedTask} onClose={() => setSelectedTask(null)} />}
    </div>
  )
}
