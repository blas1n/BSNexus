import { useParams } from 'react-router-dom'
import { useArchitectStore } from '../stores/architectStore'
import ChatMessage from '../components/architect/ChatMessage'
import ChatInput from '../components/architect/ChatInput'

export default function ArchitectPage() {
  const { sessionId } = useParams()
  const { currentSession, isLoading } = useArchitectStore()

  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const handleSend = (_message: string) => {
    // Will be implemented in Task 8.2
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] flex-col">
      <h2 className="text-2xl font-bold text-gray-900 mb-4">
        Architect {sessionId ? `- Session ${sessionId}` : ''}
      </h2>
      <div className="flex-1 overflow-y-auto space-y-2 mb-4">
        {currentSession?.messages.map((msg) => (
          <ChatMessage key={msg.id} message={msg} />
        ))}
      </div>
      <ChatInput onSend={handleSend} disabled={isLoading} />
    </div>
  )
}
