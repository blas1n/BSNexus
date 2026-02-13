import { useEffect, useRef, useCallback, useState } from 'react'

interface UseWebSocketOptions {
  url: string
  onMessage: (data: unknown) => void
  onOpen?: () => void
  onClose?: () => void
  onError?: (error: Event) => void
  reconnect?: boolean
  reconnectInterval?: number
  maxReconnectInterval?: number
  autoConnect?: boolean
}

export function useWebSocket({
  url,
  onMessage,
  onOpen,
  onClose,
  onError,
  reconnect = true,
  reconnectInterval = 1000,
  maxReconnectInterval = 30000,
  autoConnect = true,
}: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const reconnectRef = useRef(reconnect)
  const retriesRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Store callbacks in refs so connect() doesn't depend on them
  const onMessageRef = useRef(onMessage)
  const onOpenRef = useRef(onOpen)
  const onCloseRef = useRef(onClose)
  const onErrorRef = useRef(onError)

  useEffect(() => { onMessageRef.current = onMessage }, [onMessage])
  useEffect(() => { onOpenRef.current = onOpen }, [onOpen])
  useEffect(() => { onCloseRef.current = onClose }, [onClose])
  useEffect(() => { onErrorRef.current = onError }, [onError])

  useEffect(() => {
    reconnectRef.current = reconnect
  }, [reconnect])

  const connectRef = useRef<() => void>(() => {})

  const connect = useCallback(() => {
    // Don't open a new connection if one is already open or connecting
    if (
      wsRef.current?.readyState === WebSocket.OPEN ||
      wsRef.current?.readyState === WebSocket.CONNECTING
    ) {
      return
    }

    const ws = new WebSocket(url)

    ws.onopen = () => {
      retriesRef.current = 0
      setIsConnected(true)
      onOpenRef.current?.()
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      onMessageRef.current(data)
    }

    ws.onclose = () => {
      setIsConnected(false)
      wsRef.current = null
      onCloseRef.current?.()
      if (reconnectRef.current) {
        const delay = Math.min(
          reconnectInterval * Math.pow(2, retriesRef.current),
          maxReconnectInterval,
        )
        retriesRef.current += 1
        reconnectTimerRef.current = setTimeout(() => connectRef.current(), delay)
      }
    }

    ws.onerror = (error) => {
      onErrorRef.current?.(error)
    }

    wsRef.current = ws
  }, [url, reconnectInterval, maxReconnectInterval])

  useEffect(() => { connectRef.current = connect }, [connect])

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  const disconnect = useCallback(() => {
    reconnectRef.current = false
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
    wsRef.current?.close()
    wsRef.current = null
  }, [])

  useEffect(() => {
    if (autoConnect) connect()
    return () => {
      reconnectRef.current = false
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [autoConnect, connect])

  return { isConnected, send, disconnect, connect }
}
