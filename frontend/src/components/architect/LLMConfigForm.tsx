import { useState } from 'react'
import type { LLMConfigInput } from '../../types/architect'

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
    <form onSubmit={handleSubmit} className="max-w-md mx-auto space-y-4 p-6 bg-white rounded-lg border border-gray-200">
      <h3 className="text-lg font-semibold text-gray-900">Start Architect Session</h3>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
        <input
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="sk-..."
          required
          disabled={disabled}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <p className="mt-1 text-xs text-gray-400">Stored in sessionStorage only (cleared on tab close)</p>
      </div>

      <div className="relative">
        <label className="block text-sm font-medium text-gray-700 mb-1">Model</label>
        <input
          type="text"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          onFocus={() => setShowSuggestions(true)}
          onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
          placeholder="e.g. openai/gpt-4o"
          disabled={disabled}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        {showSuggestions && (
          <ul className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-md shadow-lg">
            {MODEL_SUGGESTIONS.map((suggestion) => (
              <li
                key={suggestion}
                onMouseDown={() => { setModel(suggestion); setShowSuggestions(false) }}
                className="px-3 py-2 text-sm hover:bg-blue-50 cursor-pointer"
              >
                {suggestion}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1">Base URL (optional)</label>
        <input
          type="text"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="https://your-litellm-proxy.com"
          disabled={disabled}
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      <button
        type="submit"
        disabled={disabled || !apiKey.trim()}
        className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
      >
        Start Session
      </button>
    </form>
  )
}
