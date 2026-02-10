import type { BoardResponse } from '../../types/task'
import type { Task } from '../../types/task'
import KanbanColumn from './KanbanColumn'

const columnOrder = ['waiting', 'ready', 'queued', 'in_progress', 'review', 'done', 'rejected', 'blocked']
const columnLabels: Record<string, string> = {
  waiting: 'Waiting',
  ready: 'Ready',
  queued: 'Queued',
  in_progress: 'In Progress',
  review: 'Review',
  done: 'Done',
  rejected: 'Rejected',
  blocked: 'Blocked',
}

interface Props {
  board: BoardResponse
  onTaskClick?: (task: Task) => void
}

export default function KanbanBoard({ board, onTaskClick }: Props) {
  return (
    <div className="flex gap-4 overflow-x-auto pb-4">
      {columnOrder.map((status) => (
        <KanbanColumn
          key={status}
          title={columnLabels[status]}
          tasks={board.columns[status]?.tasks ?? []}
          onTaskClick={onTaskClick}
        />
      ))}
    </div>
  )
}
