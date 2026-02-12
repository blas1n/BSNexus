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
    <div className={`bg-bg-card border border-border rounded-lg p-4 ${worker.status === 'offline' ? 'opacity-60' : ''}`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-bg-elevated text-sm font-bold text-accent-text">
            {platformIcons[worker.platform] || '?'}
          </span>
          <div>
            <h3 className="text-text-primary font-semibold text-sm">{worker.name}</h3>
            <p className="text-text-secondary text-sm">{worker.platform} / {worker.executor_type}</p>
          </div>
        </div>
        <Badge color={worker.status} label={worker.status} />
      </div>

      {worker.capabilities && Object.keys(worker.capabilities).length > 0 && (
        <div className="flex flex-wrap gap-1 mb-3">
          {Object.keys(worker.capabilities).map((cap) => (
            <span key={cap} className="bg-accent/10 text-accent-text text-xs px-2 py-0.5 rounded-md">
              {cap}
            </span>
          ))}
        </div>
      )}

      {worker.current_task_id && (
        <div className="mb-3 rounded-md bg-bg-elevated px-3 py-2">
          <span className="text-text-tertiary text-xs">
            Current task: <span className="font-mono">{worker.current_task_id.slice(0, 8)}...</span>
          </span>
        </div>
      )}

      <div className="text-text-tertiary text-xs space-y-0.5">
        {worker.last_heartbeat && (
          <p>Last heartbeat: {new Date(worker.last_heartbeat).toLocaleString()}</p>
        )}
        <p>Registered: {new Date(worker.registered_at).toLocaleString()}</p>
      </div>
    </div>
  )
}
