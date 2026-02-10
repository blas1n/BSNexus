import type { DesignSession } from '../../types/architect'

interface Props {
  sessions: DesignSession[]
  activeSessionId: string | null
  onSelect: (sessionId: string) => void
  onNew: () => void
}

export default function SessionList({ sessions, activeSessionId, onSelect, onNew }: Props) {
  return (
    <div className="w-64 border-r border-gray-200 bg-gray-50 p-4 flex flex-col h-full">
      <button
        onClick={onNew}
        className="w-full mb-4 rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
      >
        + New Session
      </button>
      <div className="flex-1 overflow-y-auto space-y-1">
        {sessions.map((session) => (
          <button
            key={session.id}
            onClick={() => onSelect(session.id)}
            className={`w-full text-left rounded-md px-3 py-2 text-sm ${
              activeSessionId === session.id
                ? 'bg-blue-100 text-blue-700 font-medium'
                : 'text-gray-700 hover:bg-gray-100'
            }`}
          >
            <div className="truncate">
              {session.messages.length > 0
                ? session.messages[0].content.slice(0, 40) + '...'
                : 'New session'}
            </div>
            <div className="text-xs text-gray-400 mt-0.5">
              {new Date(session.created_at).toLocaleDateString()}
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
