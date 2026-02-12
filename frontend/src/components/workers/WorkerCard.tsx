import type { Worker } from '../../types/worker'
import { Badge } from '../common'

const platformIcons: Record<string, string> = {
  linux: 'L',
  darwin: 'M',
  windows: 'W',
}

interface Props {
  worker: Worker
}

export default function WorkerCard({ worker }: Props) {
  return (
    <div className={`rounded-lg border border-border bg-bg-card p-4 ${worker.status === 'offline' ? 'opacity-60' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-bg-elevated text-sm font-bold text-text-secondary">
            {platformIcons[worker.platform] || '?'}
          </span>
          <div>
            <h3 className="text-sm font-semibold text-text-primary">{worker.name}</h3>
            <p className="text-xs text-text-tertiary">{worker.platform} / {worker.executor_type}</p>
          </div>
        </div>
        <Badge color={worker.status} label={worker.status} />
      </div>

      {worker.capabilities && Object.keys(worker.capabilities).length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {Object.keys(worker.capabilities).map((cap) => (
            <span key={cap} className="rounded bg-accent/10 px-1.5 py-0.5 text-xs text-accent-text">
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

      <div className="text-xs text-text-tertiary space-y-0.5">
        {worker.last_heartbeat && (
          <p>Last heartbeat: {new Date(worker.last_heartbeat).toLocaleString()}</p>
        )}
        <p>Registered: {new Date(worker.registered_at).toLocaleString()}</p>
      </div>
    </div>
  )
}
