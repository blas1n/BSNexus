import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useBoard } from '../hooks/useBoard'
import { useBoardStore } from '../stores/boardStore'
import { projectsApi } from '../api/projects'
import KanbanBoard from '../components/board/KanbanBoard'
import BoardStats from '../components/board/BoardStats'
import TaskDetail from '../components/board/TaskDetail'
import PMControl from '../components/board/PMControl'
import Header from '../components/layout/Header'
import type { Task } from '../types/task'

export default function BoardPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()

  // If no projectId is provided, show a "select project" state
  if (!projectId) {
    return (
      <>
        <Header title="Board" />
        <div className="p-8">
          <div className="rounded-lg border border-dashed border-border p-12 text-center">
            <p className="text-text-secondary mb-4">
              Select a project from the Dashboard to view its board.
            </p>
            <button
              type="button"
              onClick={() => navigate('/')}
              className="text-sm text-accent hover:underline"
            >
              Go to Dashboard
            </button>
          </div>
        </div>
      </>
    )
  }

  return <BoardContent projectId={projectId} />
}

function BoardContent({ projectId }: { projectId: string }) {
  const { isLoading } = useBoard(projectId)
  const { columns, selectedTask, setSelectedTask, isConnected } = useBoardStore()

  const { data: project } = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectsApi.get(projectId),
    enabled: !!projectId,
  })

  if (isLoading) {
    return (
      <>
        <Header title="Board" />
        <div className="flex items-center justify-center h-64">
          <div className="text-text-secondary">Loading board...</div>
        </div>
      </>
    )
  }

  return (
    <>
      <Header
        title={project?.name || 'Board'}
        action={
          <div className="flex items-center gap-2">
            <span
              className="inline-block w-2 h-2 rounded-full"
              style={{ backgroundColor: isConnected ? 'var(--status-done)' : 'var(--status-rejected)' }}
            />
            <span className="text-xs text-text-secondary">{isConnected ? 'Live' : 'Offline'}</span>
          </div>
        }
      />
      <div className="p-8">
        {/* PM Control */}
        <div className="mb-4">
          <PMControl projectId={projectId} />
        </div>

        {/* Stats bar */}
        <BoardStats projectName={project?.name} />

        {/* Kanban board */}
        <KanbanBoard columns={columns} onTaskClick={(task: Task) => setSelectedTask(task)} />

        {/* Task detail modal */}
        {selectedTask && <TaskDetail task={selectedTask} onClose={() => setSelectedTask(null)} />}
      </div>
    </>
  )
}
