import { useEffect, useRef } from 'react'

interface UseSSEOptions {
  url: string
  onMessage?: (event: MessageEvent) => void
  onError?: (error: Event) => void
  autoConnect?: boolean
}

export function useSSE({ url, onMessage, onError, autoConnect = true }: UseSSEOptions) {
  const sourceRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!autoConnect) return

    const source = new EventSource(url)
    source.onmessage = (event) => onMessage?.(event)
    source.onerror = (error) => onError?.(error)
    sourceRef.current = source

    return () => {
      source.close()
      sourceRef.current = null
    }
  }, [url, onMessage, onError, autoConnect])

  return { sourceRef }
}
