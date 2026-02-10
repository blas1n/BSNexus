import { useEffect, useRef, useCallback, useState } from 'react'

interface UseWebSocketOptions {
  url: string
  onMessage: (data: unknown) => void
  onOpen?: () => void
  onClose?: () => void
  onError?: (error: Event) => void
  reconnect?: boolean
  reconnectInterval?: number
  autoConnect?: boolean
}

export function useWebSocket({
  url,
  onMessage,
  onOpen,
  onClose,
  onError,
  reconnect = true,
  reconnectInterval = 3000,
  autoConnect = true,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const reconnectRef = useRef(reconnect)
  const connectRef = useRef<() => void>(() => {})

  useEffect(() => {
    reconnectRef.current = reconnect
  }, [reconnect])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(url)

    ws.onopen = () => {
      setIsConnected(true)
      onOpen?.()
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      onMessage(data)
    }

    ws.onclose = () => {
      setIsConnected(false)
      wsRef.current = null
      onClose?.()
      if (reconnectRef.current) {
        setTimeout(() => connectRef.current(), reconnectInterval)
      }
    }

    ws.onerror = (error) => {
      onError?.(error)
    }

    wsRef.current = ws
  }, [url, onMessage, onOpen, onClose, onError, reconnectInterval])

  useEffect(() => {
    connectRef.current = connect
  }, [connect])

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  const disconnect = useCallback(() => {
    reconnectRef.current = false
    wsRef.current?.close()
    wsRef.current = null
  }, [])

  useEffect(() => {
    if (autoConnect) connect()
    return () => {
      reconnectRef.current = false
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [autoConnect, connect])

  return { isConnected, send, disconnect, connect }
}
