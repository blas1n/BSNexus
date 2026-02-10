import { useQuery } from '@tanstack/react-query'
import { workersApi } from '../api/workers'
import WorkerList from '../components/workers/WorkerList'

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
    return <div className="text-gray-500">Loading workers...</div>
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
      <h2 className="text-2xl font-bold text-gray-900 mb-4">Workers</h2>

      {/* Summary stats */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <div className="rounded-lg border border-gray-200 bg-white p-4 text-center">
          <p className="text-2xl font-bold text-gray-900">{workerList.length}</p>
          <p className="text-sm text-gray-500">Total</p>
        </div>
        <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-center">
          <p className="text-2xl font-bold text-green-700">{idle}</p>
          <p className="text-sm text-green-600">Idle</p>
        </div>
        <div className="rounded-lg border border-orange-200 bg-orange-50 p-4 text-center">
          <p className="text-2xl font-bold text-orange-700">{busy}</p>
          <p className="text-sm text-orange-600">Busy</p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 text-center">
          <p className="text-2xl font-bold text-gray-500">{offline}</p>
          <p className="text-sm text-gray-400">Offline</p>
        </div>
      </div>

      <WorkerList workers={workerList} />
    </div>
  )
}
