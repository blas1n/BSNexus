import { useQuery } from '@tanstack/react-query'
import { workersApi } from '../api/workers'
import WorkerList from '../components/workers/WorkerList'
import { StatCard } from '../components/common'

export default function WorkersPage() {
  const { data: workers, isLoading, error } = useQuery({
    queryKey: ['workers'],
    queryFn: workersApi.list,
    refetchInterval: 10000,
  })

  const workerList = workers ?? []
  const idle = workerList.filter((w) => w.status === 'idle').length
  const busy = workerList.filter((w) => w.status === 'busy').length
  const offline = workerList.filter((w) => w.status === 'offline').length

  if (isLoading) {
    return <div className="text-text-secondary">Loading workers...</div>
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Failed to load workers. Please try again.
      </div>
    )
  }

  return (
    <div>
      <h2 className="text-2xl font-bold text-text-primary mb-4">Workers</h2>

      {/* Summary stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <StatCard label="Total" value={workerList.length} />
        <StatCard label="Idle" value={idle} badge={{ color: 'idle', label: 'Idle' }} />
        <StatCard label="Busy" value={busy} badge={{ color: 'busy', label: 'Busy' }} />
        <StatCard label="Offline" value={offline} badge={{ color: 'offline', label: 'Offline' }} />
      </div>

      <WorkerList workers={workerList} />
    </div>
  )
}
