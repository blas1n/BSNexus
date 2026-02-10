import { useQuery } from '@tanstack/react-query'
import { workersApi } from '../api/workers'
import WorkerList from '../components/workers/WorkerList'

export default function WorkersPage() {
  const { data: workers, isLoading } = useQuery({
    queryKey: ['workers'],
    queryFn: workersApi.list,
  })

  if (isLoading) return <div className="text-gray-500">Loading workers...</div>

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Workers</h2>
      <WorkerList workers={workers ?? []} />
    </div>
  )
}
