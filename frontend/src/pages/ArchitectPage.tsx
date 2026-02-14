import { useEffect, useRef, useCallback, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useArchitectStore } from '../stores/architectStore'
import type { ChatMessage as ChatMessageType } from '../stores/architectStore'
import { useWebSocket } from '../hooks/useWebSocket'
import { architectApi } from '../api/architect'
import type { DesignSession } from '../types/architect'
import ChatMessage from '../components/architect/ChatMessage'
import ChatInput from '../components/architect/ChatInput'
import SessionList from '../components/architect/SessionList'
import NewSessionModal from '../components/architect/NewSessionModal'
import FinalizePanel from '../components/architect/FinalizePanel'
import Header from '../components/layout/Header'

export default function ArchitectPage() {
  const { sessionId: paramSessionId } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
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

  const [newSessionModalOpen, setNewSessionModalOpen] = useState(false)
  const [showFinalizePanel, setShowFinalizePanel] = useState(false)
  const [designSummary, setDesignSummary] = useState('')
  const [finalizedProjectId, setFinalizedProjectId] = useState<string | null>(null)

  // Find the active session object for name display
  const activeSession = sessions.find((s) => s.id === sessionId) || null

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
      case 'finalize_ready': {
        const currentState = useArchitectStore.getState()
        const lastAssistant = [...currentState.messages].reverse().find(m => m.role === 'assistant')
        setDesignSummary(lastAssistant?.content || '')
        setShowFinalizePanel(true)
        break
      }
      case 'error':
        setStreaming(false)
        addMessage({
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `Error: ${msg.content || msg.message || 'Unknown error'}`,
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

  // Load sessions list on mount
  useEffect(() => {
    architectApi.listSessions().then((list) => {
      setSessions(list)
    }).catch(() => {
      // Failed to load sessions
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Auto-open new session modal when navigated from dashboard
  useEffect(() => {
    const state = location.state as { openNewSession?: boolean } | null
    if (state?.openNewSession) {
      setNewSessionModalOpen(true)
      // Clear the state so it doesn't re-trigger on back/forward navigation
      navigate(location.pathname, { replace: true, state: {} })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state])

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
      const chatMessages: ChatMessageType[] = session.messages.map((m) => ({
        id: m.id,
        role: m.role,
        content: m.content,
        createdAt: m.created_at,
      }))
      setMessages(chatMessages)

      // If session is already finalized, show the complete state
      if (session.status === 'finalized' && session.project_id) {
        setFinalizedProjectId(session.project_id)
        setShowFinalizePanel(true)
      } else {
        setFinalizedProjectId(null)
        setShowFinalizePanel(false)
      }
    } catch {
      // Session not found
    }
  }

  const handleCreateSession = async (config: { worker_id: string }) => {
    const session = await architectApi.createSession({
      worker_id: config.worker_id,
    })
    setSessionId(session.id)
    setNewSessionModalOpen(false)
    clearMessages()
    setSessions([session, ...sessions])
    navigate(`/architect/${session.id}`)
    // Load full session messages
    loadSession(session.id)
  }

  const handleSend = (content: string) => {
    if (!sessionId || isStreaming) return
    addMessage({
      id: crypto.randomUUID(),
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    })
    const sent = send({ type: 'message', content })
    if (!sent) {
      addMessage({
        id: crypto.randomUUID(),
        role: 'assistant',
        content: 'Error: Failed to send message. WebSocket is not connected.',
        createdAt: new Date().toISOString(),
      })
    }
  }

  const handleFinalize = async (repoPath: string) => {
    if (!sessionId) throw new Error('No active session')
    const result = await architectApi.finalize(sessionId, {
      repo_path: repoPath,
    })
    setFinalizedProjectId(result.id)
    return result
  }

  const handleNewSession = () => {
    setNewSessionModalOpen(true)
  }

  const handleSelectSession = (id: string) => {
    navigate(`/architect/${id}`)
    loadSession(id)
  }

  const headerTitle = activeSession?.name || (sessionId ? 'Architect' : 'Architect')

  // When no session is selected, show session list + empty state
  if (!sessionId) {
    return (
      <>
        <Header title="Architect" />
        <div className="flex h-[calc(100vh-8rem)]">
          <SessionList
            sessions={sessions}
            activeSessionId={null}
            onSelect={handleSelectSession}
            onNew={handleNewSession}
          />
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center space-y-4">
              <div className="text-text-tertiary text-lg">No session selected</div>
              <p className="text-text-muted text-sm">Select a session from the sidebar or create a new one.</p>
            </div>
          </div>
        </div>
        <NewSessionModal
          open={newSessionModalOpen}
          onClose={() => setNewSessionModalOpen(false)}
          onCreateSession={handleCreateSession}
        />
      </>
    )
  }

  return (
    <>
      <Header
        title={headerTitle}
        action={
          <div className="flex items-center gap-2">
            <span className={`inline-block w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
            <span className="text-xs text-text-secondary">{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
        }
      />
      <div className="flex h-[calc(100vh-8rem)]">
        <SessionList
          sessions={sessions}
          activeSessionId={sessionId}
          onSelect={handleSelectSession}
          onNew={handleNewSession}
        />
        <div className="flex-1 flex flex-col">
          {/* Messages area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {messages.length === 0 ? (
              <div className="flex-1 flex items-center justify-center h-full">
                <div className="text-center space-y-2">
                  <p className="text-lg font-medium text-text-secondary">안녕하세요! BSNexus Architect입니다.</p>
                  <p className="text-sm text-text-muted">어떤 프로젝트를 만들고 싶으신가요?</p>
                </div>
              </div>
            ) : (
              messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input area - hidden when finalize panel is showing */}
          {!showFinalizePanel && (
            <div className="p-4 border-t border-border">
              <ChatInput
                onSend={handleSend}
                disabled={isStreaming || !isConnected}
              />
            </div>
          )}
        </div>

        {/* Finalize panel (right side) */}
        {showFinalizePanel && (
          <FinalizePanel
            designSummary={designSummary}
            onConfirm={handleFinalize}
            onCancel={() => setShowFinalizePanel(false)}
            onGoToBoard={(projectId) => navigate(`/board/${projectId}`)}
            finalizedProjectId={finalizedProjectId}
          />
        )}
      </div>

      <NewSessionModal
        open={newSessionModalOpen}
        onClose={() => setNewSessionModalOpen(false)}
        onCreateSession={handleCreateSession}
      />
    </>
  )
}
