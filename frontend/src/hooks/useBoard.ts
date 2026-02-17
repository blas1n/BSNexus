import { useEffect, useCallback, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { boardApi } from '../api/board'
import { useBoardStore } from '../stores/boardStore'
import type { Task } from '../types/task'

export function useBoard(projectId: string) {
  const { setBoard, moveTask, updateTask, assignWorker, setConnected } = useBoardStore()
  const [isConnected, setLocalConnected] = useState(false)
  const sourceRef = useRef<EventSource | null>(null)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const retriesRef = useRef(0)

  const query = useQuery({
    queryKey: ['board', projectId],
    queryFn: () => boardApi.get(projectId),
    enabled: !!projectId,
  })

  const refetchRef = useRef(query.refetch)
  refetchRef.current = query.refetch

  // Set board data when query completes
  useEffect(() => {
    if (query.data) {
      setBoard(query.data)
    }
  }, [query.data, setBoard])

  const handleEvent = useCallback(
    (data: Record<string, string>) => {
      switch (data.event) {
        case 'task_moved':
        case 'task_transition':
          if (data.task_id && data.from_status && data.to_status) {
            moveTask(data.task_id, data.from_status, data.to_status)
          }
          break
        case 'task_updated':
          if (data.task) {
            try {
              updateTask(JSON.parse(data.task) as Task)
            } catch { /* ignore parse errors */ }
          }
          break
        case 'worker_assigned':
          if (data.task_id && data.worker_id) {
            assignWorker(data.task_id, data.worker_id)
          }
          break
        case 'refresh':
          refetchRef.current()
          break
      }
    },
    [moveTask, updateTask, assignWorker],
  )

  useEffect(() => {
    if (!projectId) return

    const connect = () => {
      // Clean up previous
      if (sourceRef.current) {
        sourceRef.current.close()
        sourceRef.current = null
      }

      const sseUrl = `/api/v1/board/${projectId}/events`
      const source = new EventSource(sseUrl)

      source.onopen = () => {
        retriesRef.current = 0
        setLocalConnected(true)
        setConnected(true)
      }

      source.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          handleEvent(data)
        } catch { /* ignore parse errors */ }
      }

      source.onerror = () => {
        source.close()
        sourceRef.current = null
        setLocalConnected(false)
        setConnected(false)

        // Reconnect with exponential backoff
        const delay = Math.min(1000 * Math.pow(2, retriesRef.current), 30000)
        retriesRef.current += 1
        reconnectTimerRef.current = setTimeout(connect, delay)
      }

      sourceRef.current = source
    }

    connect()

    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (sourceRef.current) {
        sourceRef.current.close()
        sourceRef.current = null
      }
      setLocalConnected(false)
      setConnected(false)
    }
  }, [projectId, handleEvent, setConnected])

  return { ...query, isConnected, refetch: query.refetch }
}
