import type { DesignMessage } from '../../types/architect'

interface Props {
  message: DesignMessage
}

export default function ChatMessage({ message }: Props) {
  const isAssistant = message.role === 'assistant'

  return (
    <div className={`flex ${isAssistant ? 'justify-start' : 'justify-end'} mb-4`}>
      <div
        className={`max-w-[70%] rounded-lg px-4 py-2 ${
          isAssistant ? 'bg-gray-100 text-gray-900' : 'bg-blue-600 text-white'
        }`}
      >
        <p className="text-sm whitespace-pre-wrap">{message.content}</p>
      </div>
    </div>
  )
}
