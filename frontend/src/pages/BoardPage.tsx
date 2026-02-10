import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useBoard } from '../hooks/useBoard'
import { useBoardStore } from '../stores/boardStore'
import { projectsApi } from '../api/projects'
import KanbanBoard from '../components/board/KanbanBoard'
import BoardStats from '../components/board/BoardStats'
import TaskDetail from '../components/board/TaskDetail'
import type { Task } from '../types/task'

export default function BoardPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const { isLoading } = useBoard(projectId!)
  const { columns, selectedTask, setSelectedTask, isConnected } = useBoardStore()

  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectsApi.get(projectId!),
    enabled: !!projectId,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading board...</div>
      </div>
    )
  }

  return (
    <div>
      {/* Header with connection status */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold text-gray-900">{project?.name || 'Kanban Board'}</h2>
        <div className="flex items-center gap-2">
          <span className={`inline-block w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-xs text-gray-500">{isConnected ? 'Live' : 'Offline'}</span>
        </div>
      </div>

      {/* Stats bar */}
      <BoardStats projectName={project?.name} />

      {/* Kanban board */}
      <KanbanBoard columns={columns} onTaskClick={(task: Task) => setSelectedTask(task)} />

      {/* Task detail modal */}
      {selectedTask && <TaskDetail task={selectedTask} onClose={() => setSelectedTask(null)} />}
    </div>
  )
}
