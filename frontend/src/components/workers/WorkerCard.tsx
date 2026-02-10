import type { Worker } from '../../types/worker'

const statusColors: Record<string, string> = {
  idle: 'bg-green-100 text-green-700',
  busy: 'bg-yellow-100 text-yellow-700',
  offline: 'bg-gray-100 text-gray-500',
}

interface Props {
  worker: Worker
}

export default function WorkerCard({ worker }: Props) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-900">{worker.name}</h3>
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusColors[worker.status]}`}>
          {worker.status}
        </span>
      </div>
      <div className="text-xs text-gray-500 space-y-1">
        <p>Platform: {worker.platform}</p>
        <p>Executor: {worker.executor_type}</p>
      </div>
    </div>
  )
}
