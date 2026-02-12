import { useState, useEffect } from 'react'
import { Modal, Button } from '../common'

interface SettingsModalProps {
  open: boolean
  onClose: () => void
}

interface LLMSettings {
  api_key: string
  default_model: string
  base_url: string
}

const STORAGE_KEY = 'llm_settings'

export function SettingsModal({ open, onClose }: SettingsModalProps) {
  const [settings, setSettings] = useState<LLMSettings>({
    api_key: '',
    default_model: '',
    base_url: '',
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved) {
        try {
          setSettings(JSON.parse(saved))
        } catch {
          /* ignore malformed data */
        }
      }
    }
  }, [open])

  const handleSave = async () => {
    setSaving(true)
    try {
      // Save to localStorage (backend API can be wired later)
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Settings"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={handleSave} loading={saving}>Save Settings</Button>
        </>
      }
    >
      <div className="space-y-6">
        <div>
          <h3 className="text-sm font-medium text-text-primary mb-4">LLM Configuration</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm text-text-secondary mb-1.5">API Key</label>
              <input
                type="password"
                value={settings.api_key}
                onChange={e => setSettings(s => ({ ...s, api_key: e.target.value }))}
                placeholder="sk-••••••••••••••••••••••"
                className="w-full px-3 py-2 bg-bg-input border border-border rounded-md text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
              />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5">Default Model</label>
              <input
                type="text"
                value={settings.default_model}
                onChange={e => setSettings(s => ({ ...s, default_model: e.target.value }))}
                placeholder="anthropic/claude-sonnet-4-20250514"
                className="w-full px-3 py-2 bg-bg-input border border-border rounded-md text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
              />
            </div>
            <div>
              <label className="block text-sm text-text-secondary mb-1.5">Base URL (Optional)</label>
              <input
                type="text"
                value={settings.base_url}
                onChange={e => setSettings(s => ({ ...s, base_url: e.target.value }))}
                placeholder="https://your-litellm-proxy.com"
                className="w-full px-3 py-2 bg-bg-input border border-border rounded-md text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
              />
            </div>
          </div>
        </div>
      </div>
    </Modal>
  )
}
