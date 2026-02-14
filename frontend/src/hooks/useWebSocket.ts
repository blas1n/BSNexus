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
  const retriesRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const shouldReconnectRef = useRef(reconnect)
  const mountedRef = useRef(true)

  // Store latest values in refs so callbacks don't go stale
  const onMessageRef = useRef(onMessage)
  const onOpenRef = useRef(onOpen)
  const onCloseRef = useRef(onClose)
  const onErrorRef = useRef(onError)
  const urlRef = useRef(url)
  const reconnectIntervalRef = useRef(reconnectInterval)
  const maxReconnectIntervalRef = useRef(maxReconnectInterval)

  useEffect(() => { onMessageRef.current = onMessage }, [onMessage])
  useEffect(() => { onOpenRef.current = onOpen }, [onOpen])
  useEffect(() => { onCloseRef.current = onClose }, [onClose])
  useEffect(() => { onErrorRef.current = onError }, [onError])
  useEffect(() => { urlRef.current = url }, [url])
  useEffect(() => { shouldReconnectRef.current = reconnect }, [reconnect])
  useEffect(() => { reconnectIntervalRef.current = reconnectInterval }, [reconnectInterval])
  useEffect(() => { maxReconnectIntervalRef.current = maxReconnectInterval }, [maxReconnectInterval])

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
  }, [])

  const closeExisting = useCallback(() => {
    clearReconnectTimer()
    if (wsRef.current) {
      // Detach handlers to prevent onclose from triggering reconnect
      wsRef.current.onopen = null
      wsRef.current.onmessage = null
      wsRef.current.onclose = null
      wsRef.current.onerror = null
      wsRef.current.close()
      wsRef.current = null
    }
  }, [clearReconnectTimer])

  const scheduleReconnect = useCallback(() => {
    if (!shouldReconnectRef.current || !mountedRef.current) return
    const currentUrl = urlRef.current
    if (!currentUrl) return

    const delay = Math.min(
      reconnectIntervalRef.current * Math.pow(2, retriesRef.current),
      maxReconnectIntervalRef.current,
    )
    retriesRef.current += 1
    reconnectTimerRef.current = setTimeout(() => {
      if (mountedRef.current && urlRef.current === currentUrl) {
        connectTo(currentUrl)
      }
    }, delay)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const connectTo = useCallback((targetUrl: string) => {
    if (!targetUrl || !mountedRef.current) return

    // Close any existing connection first
    closeExisting()

    const ws = new WebSocket(targetUrl)

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return }
      retriesRef.current = 0
      setIsConnected(true)
      onOpenRef.current?.()
    }

    ws.onmessage = (event) => {
      if (!mountedRef.current) return
      const data = JSON.parse(event.data)
      onMessageRef.current(data)
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setIsConnected(false)
      wsRef.current = null
      onCloseRef.current?.()
      scheduleReconnect()
    }

    ws.onerror = (error) => {
      onErrorRef.current?.(error)
    }

    wsRef.current = ws
  }, [closeExisting, scheduleReconnect])

  const send = useCallback((data: unknown): boolean => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
      return true
    }
    console.warn('[useWebSocket] send failed: WebSocket not open (readyState=%s)', wsRef.current?.readyState)
    return false
  }, [])

  const disconnect = useCallback(() => {
    shouldReconnectRef.current = false
    closeExisting()
    setIsConnected(false)
  }, [closeExisting])

  const connect = useCallback(() => {
    retriesRef.current = 0
    shouldReconnectRef.current = true
    connectTo(urlRef.current)
  }, [connectTo])

  // Main effect: connect/disconnect when url or autoConnect changes
  useEffect(() => {
    if (autoConnect && url) {
      retriesRef.current = 0
      connectTo(url)
    } else {
      closeExisting()
      setIsConnected(false)
    }

    return () => {
      closeExisting()
      setIsConnected(false)
    }
  }, [url, autoConnect, connectTo, closeExisting])

  // Unmount cleanup
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      closeExisting()
    }
  }, [closeExisting])

  return { isConnected, send, disconnect, connect }
}
