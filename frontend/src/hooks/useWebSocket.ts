import { useEffect, useRef, useCallback } from 'react'

interface UseWebSocketOptions {
  url: string
  onMessage?: (data: unknown) => void
  onOpen?: () => void
  onClose?: () => void
  onError?: (error: Event) => void
  autoConnect?: boolean
}

export function useWebSocket({ url, onMessage, onOpen, onClose, onError, autoConnect = true }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)

  const connect = useCallback(() => {
    const ws = new WebSocket(url)

    ws.onopen = () => onOpen?.()
    ws.onclose = () => onClose?.()
    ws.onerror = (e) => onError?.(e)
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      onMessage?.(data)
    }

    wsRef.current = ws
  }, [url, onMessage, onOpen, onClose, onError])

  const disconnect = useCallback(() => {
    wsRef.current?.close()
    wsRef.current = null
  }, [])

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  useEffect(() => {
    if (autoConnect) connect()
    return () => disconnect()
  }, [autoConnect, connect, disconnect])

  return { connect, disconnect, send }
}
