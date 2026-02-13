import { useState } from 'react'
import type { LLMConfigInput } from '../../types/architect'
import { Button } from '../common'

const MODEL_SUGGESTIONS = [
  'anthropic/claude-sonnet-4-20250514',
  'openai/gpt-4o',
]

interface Props {
  onSubmit: (config: LLMConfigInput) => void
  disabled?: boolean
}

export default function LLMConfigForm({ onSubmit, disabled }: Props) {
  const [apiKey, setApiKey] = useState(() => sessionStorage.getItem('llm_api_key') || '')
  const [model, setModel] = useState(MODEL_SUGGESTIONS[0])
  const [baseUrl, setBaseUrl] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!apiKey.trim()) return
    sessionStorage.setItem('llm_api_key', apiKey)
    onSubmit({
      api_key: apiKey,
      model: model || undefined,
      base_url: baseUrl || undefined,
    })
  }

  return (
    <form onSubmit={handleSubmit} className="max-w-md mx-auto space-y-4 p-6 bg-bg-card rounded-lg border border-border">
      <h3 className="text-lg font-semibold text-text-primary">Start Architect Session</h3>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-1">API Key</label>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="sk-..."
          required
          disabled={disabled}
          className="w-full rounded-md border border-border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
        />
        <p className="mt-1 text-xs text-text-tertiary">Stored in sessionStorage only (cleared on tab close)</p>
      </div>

      <div className="relative">
        <label className="block text-sm font-medium text-text-primary mb-1">Model</label>
        <input
          type="text"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          onFocus={() => setShowSuggestions(true)}
          onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
          placeholder="e.g. openai/gpt-4o"
          disabled={disabled}
          className="w-full rounded-md border border-border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
        />
        {showSuggestions && (
          <ul className="absolute z-10 mt-1 w-full bg-bg-card border border-border rounded-md shadow-lg">
            {MODEL_SUGGESTIONS.map((suggestion) => (
              <li
                key={suggestion}
                onMouseDown={() => { setModel(suggestion); setShowSuggestions(false) }}
                className="px-3 py-2 text-sm hover:bg-accent/10 cursor-pointer"
              >
                {suggestion}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-text-primary mb-1">Base URL (optional)</label>
        <input
          type="text"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://your-litellm-proxy.com"
          disabled={disabled}
          className="w-full rounded-md border border-border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent"
        />
      </div>

      <Button
        type="submit"
        disabled={disabled || !apiKey.trim()}
        className="w-full"
      >
        Start Session
      </Button>
    </form>
  )
}
