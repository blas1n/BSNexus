import { useEffect, useRef, useCallback, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useArchitectStore } from '../stores/architectStore'
import type { ChatMessage as ChatMessageType } from '../stores/architectStore'
import { useWebSocket } from '../hooks/useWebSocket'
import { architectApi } from '../api/architect'
import type { DesignSession } from '../types/architect'
import type { Project } from '../types/project'
import ChatMessage from '../components/architect/ChatMessage'
import ChatInput from '../components/architect/ChatInput'
import SessionList from '../components/architect/SessionList'
import NewSessionModal from '../components/architect/NewSessionModal'
import FinalizeDialog from '../components/architect/FinalizeDialog'
import DesignPreview from '../components/architect/DesignPreview'
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
  const [showFinalizeDialog, setShowFinalizeDialog] = useState(false)
  const [finalizedProject, setFinalizedProject] = useState<Project | null>(null)

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
    send({ type: 'message', content })
  }

  const handleFinalize = async (repoPath: string) => {
    if (!sessionId) throw new Error('No active session')
    const project = await architectApi.finalize(sessionId, {
      repo_path: repoPath,
    })
    setShowFinalizeDialog(false)
    setFinalizedProject(project)
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
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className={`inline-block w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
              <span className="text-xs text-text-secondary">{isConnected ? 'Connected' : 'Disconnected'}</span>
            </div>
            {messages.some((m) => m.role === 'user') && !isStreaming && (
              <button
                onClick={() => setShowFinalizeDialog(true)}
                className="px-3 py-1.5 text-sm font-medium rounded-md bg-green-600 text-white hover:bg-green-700 transition-colors"
              >
                Finalize
              </button>
            )}
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

          {/* Input area */}
          <div className="p-4 border-t border-border">
            <ChatInput
              onSend={handleSend}
              disabled={isStreaming || !isConnected}
            />
          </div>
        </div>

        {/* Design preview sidebar (when finalized) */}
        {finalizedProject && (
          <div className="w-80 border-l border-border overflow-y-auto p-4">
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

      <NewSessionModal
        open={newSessionModalOpen}
        onClose={() => setNewSessionModalOpen(false)}
        onCreateSession={handleCreateSession}
      />
    </>
  )
}
