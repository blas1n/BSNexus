import type { DesignSession } from '../../types/architect'
import { Button } from '../common'

interface Props {
  sessions: DesignSession[]
  activeSessionId: string | null
  onSelect: (sessionId: string) => void
  onNew: () => void
}

export default function SessionList({ sessions, activeSessionId, onSelect, onNew }: Props) {
  return (
    <div className="w-64 border-r border-border bg-bg-surface p-4 flex flex-col h-full">
      <Button
        onClick={onNew}
        className="w-full mb-4"
      >
        + New Session
      </Button>
      <div className="flex-1 overflow-y-auto space-y-1">
        {sessions.map((session) => (
          <button
            key={session.id}
            onClick={() => onSelect(session.id)}
            className={`w-full text-left rounded-md px-3 py-2 text-sm ${
              activeSessionId === session.id
                ? 'bg-accent/10 text-accent-text font-medium'
                : 'text-text-primary hover:bg-bg-hover'
            }`}
          >
            <div className="truncate">
              {session.messages.length > 0
                ? session.messages[0].content.slice(0, 40) + '...'
                : 'New session'}
            </div>
            <div className="text-xs text-text-tertiary mt-0.5">
              {new Date(session.created_at).toLocaleDateString()}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
