import { useBoardStore } from '../../stores/boardStore'

const statusColors: Record<string, string> = {
  waiting: 'bg-gray-400',
  ready: 'bg-blue-400',
  queued: 'bg-yellow-400',
  in_progress: 'bg-orange-400',
  review: 'bg-purple-400',
  done: 'bg-green-400',
  rejected: 'bg-red-400',
  blocked: 'bg-red-300',
}

interface Props {
  projectName?: string
}

export default function BoardStats({ projectName }: Props) {
  const { stats, workers, getBoardStats } = useBoardStore()
  const { total, done, completionRate } = getBoardStats()
  const activeWorkers = Object.values(workers).reduce((sum, count) => sum + count, 0)

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 mb-4">
      <div className="flex items-center justify-between flex-wrap gap-4">
        {projectName && (
          <h3 className="text-lg font-semibold text-gray-900">{projectName}</h3>
        )}

        <div className="flex items-center gap-6">
          <div className="text-sm text-gray-600">
            <span className="font-medium">{total}</span> tasks
          </div>

          <div className="flex items-center gap-2">
            <div className="w-32 h-2 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-green-500 rounded-full transition-all duration-500"
                style={{ width: `${completionRate}%` }}
              />
            </div>
            <span className="text-sm text-gray-600">
              {done}/{total} ({Math.round(completionRate)}%)
            </span>
          </div>

          <div className="flex items-center gap-2">
            {Object.entries(stats).map(([status, count]) => (
              <div key={status} className="flex items-center gap-1" title={status}>
                <span
                  className={`inline-block w-2.5 h-2.5 rounded-full ${statusColors[status] || 'bg-gray-300'}`}
                />
                <span className="text-xs text-gray-500">{count}</span>
              </div>
            ))}
          </div>

          <div className="text-sm text-gray-600">
            <span className="font-medium">{activeWorkers}</span> workers
          </div>
        </div>
      </div>
    </div>
  )
}
