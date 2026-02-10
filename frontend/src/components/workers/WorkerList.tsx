import type { Worker } from '../../types/worker'
import WorkerCard from './WorkerCard'

interface Props {
  workers: Worker[]
}

export default function WorkerList({ workers }: Props) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {workers.map((worker) => (
        <WorkerCard key={worker.id} worker={worker} />
      ))}
    </div>
  )
}
