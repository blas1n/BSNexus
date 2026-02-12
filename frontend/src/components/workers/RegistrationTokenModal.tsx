import { useState, useCallback } from 'react'
import { Modal, Button } from '../common'

interface RegistrationTokenModalProps {
  open: boolean
  onClose: () => void
}

function generateToken(): string {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
  const random = Array.from({ length: 20 }, () => chars[Math.floor(Math.random() * chars.length)]).join('')
  return `glrt-${random}`
}

export default function RegistrationTokenModal({ open, onClose }: RegistrationTokenModalProps) {
  const [token] = useState(generateToken)
  const [copied, setCopied] = useState(false)

  const command = `bsnexus-worker register \\
  --url http://localhost:8000 \\
  --token ${token} \\
  --executor claude-code`

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(command)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [command])

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Registration Token"
      footer={<Button variant="secondary" onClick={onClose}>Close</Button>}
    >
      <div className="space-y-4">
        <p className="text-text-secondary text-sm">
          Run this command on the worker machine to register it with this server.
        </p>

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
      </div>
    </Modal>
  )
}
