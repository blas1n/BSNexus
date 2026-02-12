import { useState } from 'react'
import { Modal, Button } from '../common'

interface Props {
  onConfirm: (repoPath: string) => Promise<void>
  onCancel: () => void
}

export default function FinalizeDialog({ onConfirm, onCancel }: Props) {
  const [repoPath, setRepoPath] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    setIsLoading(true)
    setError(null)
    try {
      await onConfirm(repoPath)
    } catch (err: unknown) {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined
      setError(detail || 'Failed to finalize design. Please try again.')
    } finally {
      setIsLoading(false)
    }
  }

  const footer = (
    <>
      <Button variant="secondary" onClick={onCancel} disabled={isLoading}>
        Cancel
      </Button>
      <Button
        onClick={handleSubmit}
        disabled={!repoPath.trim() || isLoading}
        loading={isLoading}
        className="bg-green-600 hover:bg-green-700"
      >
        {isLoading ? 'Finalizing...' : 'Finalize'}
      </Button>
    </>
  )

  return (
    <Modal open={true} onClose={onCancel} title="Finalize Design" footer={footer} width={448}>
      <p className="text-sm text-text-secondary mb-4">
        This will create a project from the current design. Please provide the repository path.
      </p>
      {error && (
        <div className="mb-4 rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
          {error}
        </div>
      )}
      <div>
        <label className="block text-sm font-medium text-text-primary mb-1">Repository Path</label>
        <input
          type="text"
          value={repoPath}
          onChange={(e) => setRepoPath(e.target.value)}
          placeholder="/path/to/repo"
          disabled={isLoading}
          className="w-full rounded-md border border-border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent disabled:bg-bg-elevated"
        />
      </div>
    </Modal>
  )
}
