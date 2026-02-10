import { useEffect, useRef, useCallback, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useArchitectStore } from '../stores/architectStore'
import type { ChatMessage as ChatMessageType } from '../stores/architectStore'
import { useWebSocket } from '../hooks/useWebSocket'
import { architectApi } from '../api/architect'
import type { LLMConfigInput, DesignSession } from '../types/architect'
import type { Project } from '../types/project'
import ChatMessage from '../components/architect/ChatMessage'
import ChatInput from '../components/architect/ChatInput'
import SessionList from '../components/architect/SessionList'
import LLMConfigForm from '../components/architect/LLMConfigForm'
import FinalizeDialog from '../components/architect/FinalizeDialog'
import DesignPreview from '../components/architect/DesignPreview'

export default function ArchitectPage() {
  const { sessionId: paramSessionId } = useParams()
  const navigate = useNavigate()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const {
    sessionId,
    sessions,
    messages,
    isStreaming,
    isConnected,
    setSessionId,
    setSessions,
    setMessages,
    addMessage,
    appendToLastMessage,
    setStreaming,
    setConnected,
    clearMessages,
  } = useArchitectStore()

  const [showConfig, setShowConfig] = useState(!sessionId)
  const [showFinalizeDialog, setShowFinalizeDialog] = useState(false)
  const [finalizedProject, setFinalizedProject] = useState<Project | null>(null)

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // WebSocket message handler
  const handleWsMessage = useCallback((data: unknown) => {
    const msg = data as { type: string; content?: string; message?: string }
    switch (msg.type) {
      case 'chunk':
        if (!useArchitectStore.getState().isStreaming) {
          setStreaming(true)
          addMessage({
            id: crypto.randomUUID(),
            role: 'assistant',
            content: msg.content || '',
            isStreaming: true,
            createdAt: new Date().toISOString(),
          })
        } else {
          appendToLastMessage(msg.content || '')
        }
        break
      case 'done': {
        setStreaming(false)
        const state = useArchitectStore.getState()
        const updated = [...state.messages]
        if (updated.length > 0) {
          const last = updated[updated.length - 1]
          updated[updated.length - 1] = { ...last, content: msg.content || last.content, isStreaming: false }
          setMessages(updated)
        }
        break
      }
      case 'error':
        setStreaming(false)
        addMessage({
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `Error: ${msg.message || 'Unknown error'}`,
          createdAt: new Date().toISOString(),
        })
        break
    }
  }, [addMessage, appendToLastMessage, setStreaming, setMessages])

  const wsUrl = sessionId
    ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/architect/${sessionId}`
    : ''

  const { send, isConnected: wsConnected } = useWebSocket({
    url: wsUrl,
    onMessage: handleWsMessage,
    onOpen: () => setConnected(true),
    onClose: () => setConnected(false),
    reconnect: true,
    autoConnect: !!sessionId,
  })

  useEffect(() => {
    setConnected(wsConnected)
  }, [wsConnected, setConnected])

  // Load session from URL param
  useEffect(() => {
    if (paramSessionId && paramSessionId !== sessionId) {
      loadSession(paramSessionId)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramSessionId])

  const loadSession = async (id: string) => {
    try {
      const session: DesignSession = await architectApi.getSession(id)
      setSessionId(id)
      setShowConfig(false)
      const chatMessages: ChatMessageType[] = session.messages.map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        createdAt: m.created_at,
      }))
      setMessages(chatMessages)
    } catch {
      // Session not found
    }
  }

  const handleCreateSession = async (config: LLMConfigInput) => {
    try {
      const session = await architectApi.createSession({ llm_config: config })
      setSessionId(session.id)
      setShowConfig(false)
      clearMessages()
      setSessions([session, ...sessions])
      navigate(`/architect/${session.id}`)
    } catch {
      // Error creating session
    }
  }

  const handleSend = (content: string) => {
    if (!sessionId || isStreaming) return
    addMessage({
      id: crypto.randomUUID(),
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    })
    send({ type: 'message', content })
  }

  const handleFinalize = async (repoPath: string) => {
    if (!sessionId) return
    setShowFinalizeDialog(false)
    try {
      const apiKey = sessionStorage.getItem('llm_api_key') || ''
      const project = await architectApi.finalize(sessionId, {
        repo_path: repoPath,
        pm_llm_config: apiKey ? { api_key: apiKey } : undefined,
      })
      setFinalizedProject(project)
    } catch {
      addMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: 'Error: Failed to finalize design.',
        createdAt: new Date().toISOString(),
      })
    }
  }

  const handleNewSession = () => {
    setSessionId(null)
    clearMessages()
    setShowConfig(true)
    setFinalizedProject(null)
    navigate('/architect')
  }

  const handleSelectSession = (id: string) => {
    navigate(`/architect/${id}`)
    loadSession(id)
  }

  // Show config form if no session
  if (showConfig && !sessionId) {
    return (
      <div className="flex h-[calc(100vh-8rem)]">
        <SessionList
          sessions={sessions}
          activeSessionId={null}
          onSelect={handleSelectSession}
          onNew={handleNewSession}
        />
        <div className="flex-1 flex items-center justify-center">
          <LLMConfigForm onSubmit={handleCreateSession} />
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-8rem)]">
      <SessionList
        sessions={sessions}
        activeSessionId={sessionId}
        onSelect={handleSelectSession}
        onNew={handleNewSession}
      />
      <div className="flex-1 flex flex-col">
        {/* Connection status */}
        <div className="px-4 py-2 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Architect Chat</h2>
          <div className="flex items-center gap-2">
            <span className={`inline-block w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-xs text-gray-500">{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>

        {/* Messages area */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="p-4 border-t border-gray-200">
          <ChatInput
            onSend={handleSend}
            onFinalize={() => setShowFinalizeDialog(true)}
            disabled={isStreaming || !isConnected}
            showFinalize={messages.length > 0 && !isStreaming}
          />
        </div>
      </div>

      {/* Design preview sidebar (when finalized) */}
      {finalizedProject && (
        <div className="w-80 border-l border-gray-200 overflow-y-auto p-4">
          <DesignPreview
            project={finalizedProject}
            onConfirm={() => navigate(`/board/${finalizedProject.id}`)}
          />
        </div>
      )}

      {/* Finalize dialog */}
      {showFinalizeDialog && (
        <FinalizeDialog
          onConfirm={handleFinalize}
          onCancel={() => setShowFinalizeDialog(false)}
        />
      )}
    </div>
  )
}
