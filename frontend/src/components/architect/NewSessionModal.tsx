import { useState, useEffect } from 'react'
import { Modal, Button } from '../common'

interface LLMSettings {
  api_key: string
  default_model: string
  base_url: string
}

const LLM_SETTINGS_KEY = 'llm_settings'

const MODEL_SUGGESTIONS = [
  'anthropic/claude-sonnet-4-20250514',
  'openai/gpt-4o',
]

interface NewSessionModalProps {
  open: boolean
  onClose: () => void
  onCreateSession: (config: { model: string; api_key: string; base_url?: string; name?: string }) => void
}

export default function NewSessionModal({ open, onClose, onCreateSession }: NewSessionModalProps) {
  const [sessionName, setSessionName] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [model, setModel] = useState(MODEL_SUGGESTIONS[0])
  const [baseUrl, setBaseUrl] = useState('')
  const [hasStoredSettings, setHasStoredSettings] = useState(false)
  const [showSuggestions, setShowSuggestions] = useState(false)

  useEffect(() => {
    if (open) {
      const saved = localStorage.getItem(LLM_SETTINGS_KEY)
      if (saved) {
        try {
          const settings: LLMSettings = JSON.parse(saved)
          if (settings.api_key) {
            setApiKey(settings.api_key)
            setHasStoredSettings(true)
          }
          if (settings.default_model) {
            setModel(settings.default_model)
          }
          if (settings.base_url) {
            setBaseUrl(settings.base_url)
          }
        } catch {
          /* ignore malformed data */
        }
      }
      // Also check sessionStorage for legacy key
      const sessionKey = sessionStorage.getItem('llm_api_key')
      if (sessionKey && !apiKey) {
        setApiKey(sessionKey)
        setHasStoredSettings(true)
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const handleCreate = () => {
    if (!apiKey.trim()) return
    sessionStorage.setItem('llm_api_key', apiKey)
    onCreateSession({
      api_key: apiKey,
      model: model || MODEL_SUGGESTIONS[0],
      base_url: baseUrl || undefined,
      name: sessionName.trim() || undefined,
    })
    // Reset form
    setSessionName('')
  }

  const footer = (
    <>
      <Button variant="secondary" onClick={onClose}>
        Cancel
      </Button>
      <Button onClick={handleCreate} disabled={!apiKey.trim()}>
        Create Session
      </Button>
    </>
  )

  return (
    <Modal open={open} onClose={onClose} title="New Session" footer={footer} width={448}>
      <div className="space-y-4">
        <div>
          <label className="block text-sm text-text-secondary mb-1.5">Session Name (optional)</label>
          <input
            type="text"
            value={sessionName}
            onChange={(e) => setSessionName(e.target.value)}
            placeholder="e.g. E-commerce API Design"
            className="w-full px-3 py-2 bg-bg-input border border-border rounded-md text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
          />
        </div>

        {hasStoredSettings && (
          <div className="rounded-md bg-accent/5 border border-accent/20 px-3 py-2">
            <p className="text-sm text-text-secondary">
              Using saved LLM settings with model <span className="font-medium text-text-primary">{model}</span>
            </p>
          </div>
        )}

        <div>
          <label className="block text-sm text-text-secondary mb-1.5">API Key</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="sk-..."
            className="w-full px-3 py-2 bg-bg-input border border-border rounded-md text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
          />
          <p className="mt-1 text-xs text-text-tertiary">Stored in sessionStorage only (cleared on tab close)</p>
        </div>

        <div className="relative">
          <label className="block text-sm text-text-secondary mb-1.5">Model</label>
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            onFocus={() => setShowSuggestions(true)}
            onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
            placeholder="e.g. openai/gpt-4o"
            className="w-full px-3 py-2 bg-bg-input border border-border rounded-md text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
          />
          {showSuggestions && (
            <ul className="absolute z-10 mt-1 w-full bg-bg-card border border-border rounded-md shadow-lg">
              {MODEL_SUGGESTIONS.map((suggestion) => (
                <li
                  key={suggestion}
                  onMouseDown={() => { setModel(suggestion); setShowSuggestions(false) }}
                  className="px-3 py-2 text-sm text-text-primary hover:bg-accent/10 cursor-pointer"
                >
                  {suggestion}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <label className="block text-sm text-text-secondary mb-1.5">Base URL (optional)</label>
          <input
            type="text"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://your-litellm-proxy.com"
            className="w-full px-3 py-2 bg-bg-input border border-border rounded-md text-text-primary text-sm placeholder:text-text-muted focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent"
          />
        </div>
      </div>
    </Modal>
  )
}
