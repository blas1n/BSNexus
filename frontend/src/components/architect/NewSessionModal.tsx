import { useState, useEffect } from 'react'
import { Modal, Button } from '../common'
import { workersApi } from '../../api/workers'
import type { Worker } from '../../types/worker'

interface NewSessionModalProps {
  open: boolean
  onClose: () => void
  onCreateSession: (config: { worker_id: string }) => Promise<void>
}

export default function NewSessionModal({ open, onClose, onCreateSession }: NewSessionModalProps) {
  const [workers, setWorkers] = useState<Worker[]>([])
  const [selectedWorkerId, setSelectedWorkerId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [creating, setCreating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setLoading(true)
      setError(null)
      workersApi.list()
        .then((list) => {
          setWorkers(list)
          if (list.length > 0 && !selectedWorkerId) {
            setSelectedWorkerId(list[0].id)
          }
        })
        .catch(() => {
          setWorkers([])
        })
        .finally(() => setLoading(false))
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const handleCreate = async () => {
    if (!selectedWorkerId) return
    setCreating(true)
    setError(null)
    try {
      await onCreateSession({ worker_id: selectedWorkerId })
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } }
      setError(axiosErr.response?.data?.detail || 'Failed to create session')
    } finally {
      setCreating(false)
    }
  }

  const selectedWorker = workers.find((w) => w.id === selectedWorkerId)

  const footer = (
    <>
      <Button variant="secondary" onClick={onClose}>
        Cancel
      </Button>
      <Button onClick={handleCreate} disabled={!selectedWorkerId || creating} loading={creating}>
        Create Session
      </Button>
    </>
  )

  return (
    <Modal open={open} onClose={onClose} title="New Session" footer={footer} width={520}>
      <div className="space-y-3">
        {error && (
          <p className="text-sm text-red-500">{error}</p>
        )}
        {/* Section header */}
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-text-primary tracking-wide">Select Worker</span>
          <span className="text-[11px] text-text-muted">(cannot be changed after creation)</span>
        </div>

        {/* Worker list */}
        {loading ? (
          <div className="py-8 text-center text-sm text-text-muted">Loading workers...</div>
        ) : workers.length === 0 ? (
          <div className="py-8 text-center text-sm text-text-muted">No workers registered</div>
        ) : (
          <div className="space-y-1.5">
            {workers.map((worker) => {
              const isSelected = worker.id === selectedWorkerId
              const isOnline = worker.status !== 'offline'
              return (
                <button
                  key={worker.id}
                  onClick={() => setSelectedWorkerId(worker.id)}
                  className={`w-full flex items-center justify-between h-11 px-3 rounded-lg border transition-colors ${
                    isSelected
                      ? 'bg-bg-hover border-accent'
                      : 'bg-bg-input border-border-subtle hover:border-border'
                  }`}
                >
                  <div className="flex items-center gap-2.5">
                    {/* Radio indicator */}
                    <span
                      className={`flex items-center justify-center w-[18px] h-[18px] rounded-full border-2 transition-colors ${
                        isSelected ? 'border-accent bg-accent' : 'border-border'
                      }`}
                    >
                      {isSelected && (
                        <span className="w-2 h-2 rounded-full bg-white" />
                      )}
                    </span>
                    <span className={`text-[13px] font-medium ${isSelected ? 'text-text-primary' : 'text-text-secondary'}`}>
                      {worker.name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[11px] font-mono text-text-muted">{worker.platform}</span>
                    <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-500' : 'bg-gray-500'}`} />
                  </div>
                </button>
              )
            })}
          </div>
        )}

        {/* Selection status */}
        {selectedWorker && (
          <p className="text-xs text-text-muted">{selectedWorker.name} selected</p>
        )}
      </div>
    </Modal>
  )
}
