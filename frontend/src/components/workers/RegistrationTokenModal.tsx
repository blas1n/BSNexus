import { useState, useCallback, useEffect } from 'react'
import { Modal, Button } from '../common'
import { registrationTokensApi } from '../../api/workers'

interface RegistrationTokenModalProps {
  open: boolean
  onClose: () => void
}

export default function RegistrationTokenModal({ open, onClose }: RegistrationTokenModalProps) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Registration Token"
      footer={<Button variant="secondary" onClick={onClose}>Close</Button>}
    >
      {open && <RegistrationTokenContent />}
    </Modal>
  )
}

function RegistrationTokenContent() {
  const [token, setToken] = useState<string | null>(null)
  const [serverUrl, setServerUrl] = useState<string | null>(null)
  const [redisUrl, setRedisUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    registrationTokensApi
      .create()
      .then((res) => {
        setToken(res.token)
        setServerUrl(res.server_url ?? null)
        setRedisUrl(res.redis_url ?? null)
      })
      .catch(() => setError('Failed to create registration token'))
      .finally(() => setLoading(false))
  }, [])

  const command = token
    ? `bsnexus-worker register \\\n  --url ${serverUrl ?? 'http://<SERVER_HOST>:8000'} \\\n  --token ${token} \\\n  --redis-url ${redisUrl ?? 'redis://localhost:6379'} \\\n  --executor claude-code`
    : ''

  const handleCopy = useCallback(async () => {
    if (!command) return
    await navigator.clipboard.writeText(command)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [command])

  return (
    <div className="space-y-4">
      <p className="text-text-secondary text-sm">
        Run this command on the worker machine to register it with this server.
      </p>

      {loading && (
        <p className="text-text-secondary text-sm">Generating token...</p>
      )}

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {token && (
        <>
          {/* Token field */}
          <div className="space-y-1.5">
            <label className="text-text-secondary text-sm">Token</label>
            <input
              type="text"
              value={token}
              readOnly
              className="w-full bg-bg-input border border-border rounded-md px-3 py-2 text-text-primary text-sm focus:outline-none"
            />
          </div>

          {/* Command field */}
          <div className="space-y-1.5">
            <label className="text-text-secondary text-sm">Command</label>
            <div className="bg-bg-elevated rounded-md p-4 font-mono text-sm text-accent-text whitespace-pre-wrap break-all">
              {command}
            </div>
            <Button variant="secondary" size="sm" onClick={handleCopy}>
              {copied ? 'Copied!' : 'Copy'}
            </Button>
          </div>
        </>
      )}
    </div>
  )
}
