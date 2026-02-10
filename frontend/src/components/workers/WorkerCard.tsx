import type { Worker } from '../../types/worker'

const statusColors: Record<string, { bg: string; text: string; dot: string }> = {
  idle: { bg: 'bg-green-50', text: 'text-green-700', dot: 'bg-green-500' },
  busy: { bg: 'bg-orange-50', text: 'text-orange-700', dot: 'bg-orange-500' },
  offline: { bg: 'bg-gray-50', text: 'text-gray-500', dot: 'bg-gray-400' },
}

const platformIcons: Record<string, string> = {
  linux: 'L',
  darwin: 'M',
  windows: 'W',
}

interface Props {
  worker: Worker
}

export default function WorkerCard({ worker }: Props) {
  const colors = statusColors[worker.status] || statusColors.offline
  const capabilities = worker.capabilities ? Object.keys(worker.capabilities) : []

  return (
    <div className={`rounded-lg border border-gray-200 bg-white p-4 ${worker.status === 'offline' ? 'opacity-60' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-gray-100 text-sm font-bold text-gray-600">
            {platformIcons[worker.platform] || '?'}
          </span>
          <div>
            <h3 className="text-sm font-semibold text-gray-900">{worker.name}</h3>
            <p className="text-xs text-gray-400">{worker.platform} / {worker.executor_type}</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className={`inline-block w-2 h-2 rounded-full ${colors.dot}`} />
          <span className={`text-xs font-medium ${colors.text}`}>{worker.status}</span>
        </div>
      </div>

      {capabilities.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {capabilities.map((cap) => (
            <span key={cap} className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-600">
              {cap}
            </span>
          ))}
        </div>
      )}

      {worker.current_task_id && (
        <div className="mb-3 rounded-md bg-orange-50 px-3 py-2">
          <span className="text-xs text-orange-700">
            Current task: <span className="font-mono">{worker.current_task_id.slice(0, 8)}...</span>
          </span>
        </div>
      )}

      <div className="text-xs text-gray-400 space-y-0.5">
        {worker.last_heartbeat && (
          <p>Last heartbeat: {new Date(worker.last_heartbeat).toLocaleString()}</p>
        )}
        <p>Registered: {new Date(worker.registered_at).toLocaleString()}</p>
      </div>
    </div>
  )
}
