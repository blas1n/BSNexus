import { useState } from 'react'
import type { Worker, WorkerStatus } from '../../types/worker'
import WorkerCard from './WorkerCard'

type FilterStatus = WorkerStatus | 'all'

interface Props {
  workers: Worker[]
}

export default function WorkerList({ workers }: Props) {
  const [filter, setFilter] = useState<FilterStatus>('all')

  const filters: { label: string; value: FilterStatus }[] = [
    { label: 'All', value: 'all' },
    { label: 'Idle', value: 'idle' },
    { label: 'Busy', value: 'busy' },
    { label: 'Offline', value: 'offline' },
  ]

  const filtered = filter === 'all' ? workers : workers.filter((w) => w.status === filter)

  const counts = {
    all: workers.length,
    idle: workers.filter((w) => w.status === 'idle').length,
    busy: workers.filter((w) => w.status === 'busy').length,
    offline: workers.filter((w) => w.status === 'offline').length,
  }

  return (
    <div>
      {/* Filter tabs */}
      <div className="flex gap-2 mb-4">
        {filters.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === f.value
                ? 'bg-accent/10 text-accent-text'
                : 'bg-bg-elevated text-text-secondary hover:bg-bg-hover'
            }`}
          >
            {f.label} ({counts[f.value]})
          </button>
        ))}
      </div>

      {/* Worker grid */}
      {filtered.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-text-tertiary">
          No {filter === 'all' ? '' : filter} workers found
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((worker) => (
            <WorkerCard key={worker.id} worker={worker} />
          ))}
        </div>
      )}
    </div>
  )
}
