import { useQuery } from '@tanstack/react-query'
import { workersApi } from '../api/workers'
import WorkerList from '../components/workers/WorkerList'
import { StatCard, Button } from '../components/common'
import Header from '../components/layout/Header'

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
    return (
      <>
        <Header title="Workers" />
        <div className="p-8 text-text-secondary">Loading workers...</div>
      </>
    )
  }

  if (error) {
    return (
      <>
        <Header title="Workers" />
        <div className="p-8">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Failed to load workers. Please try again.
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <Header title="Workers" action={<Button size="sm">Registration Token</Button>} />
      <div className="p-8">
        {/* Summary stats */}
        <div className="grid grid-cols-4 gap-4 mb-6">
          <StatCard label="Total" value={workerList.length} />
          <StatCard label="Idle" value={idle} badge={{ color: 'idle', label: 'Idle' }} />
          <StatCard label="Busy" value={busy} badge={{ color: 'busy', label: 'Busy' }} />
          <StatCard label="Offline" value={offline} badge={{ color: 'offline', label: 'Offline' }} />
        </div>

        <WorkerList workers={workerList} />
      </div>
    </>
  )
}
