import type { DesignSession } from '../../types/architect'
import { Button } from '../common'

interface Props {
  sessions: DesignSession[]
  activeSessionId: string | null
  onSelect: (sessionId: string) => void
  onNew: () => void
}

function getSessionLabel(session: DesignSession): string {
  if (session.name) return session.name
  if (session.messages.length > 0) {
    const firstUserMsg = session.messages.find((m) => m.role === 'user')
    if (firstUserMsg) return firstUserMsg.content.slice(0, 40)
  }
  return 'New Session'
}

export default function SessionList({ sessions, activeSessionId, onSelect, onNew }: Props) {
  return (
    <div className="w-[260px] border-r border-border bg-bg-surface flex flex-col h-full">
      <div className="p-4 flex items-center justify-between">
        <h2 className="text-text-primary font-semibold text-sm">Sessions</h2>
        <Button variant="primary" size="sm" onClick={onNew}>
          + New
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
        {sessions.map((session) => {
          const isActive = activeSessionId === session.id
          return (
            <button
              key={session.id}
              onClick={() => onSelect(session.id)}
              className={`w-full text-left rounded-md px-3 py-2.5 text-sm transition-colors ${
                isActive
                  ? 'bg-accent/10 border-l-2 border-accent'
                  : 'hover:bg-bg-hover border-l-2 border-transparent'
              }`}
            >
              <div className={`truncate ${isActive ? 'font-semibold text-text-primary' : 'text-text-primary'}`}>
                {getSessionLabel(session)}
              </div>
              <div className="text-xs text-text-tertiary mt-0.5">
                {new Date(session.created_at).toLocaleDateString()}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
