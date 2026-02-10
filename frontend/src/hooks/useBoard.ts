import { useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { boardApi } from '../api/board'
import { useBoardStore } from '../stores/boardStore'
import { useWebSocket } from './useWebSocket'
import type { Task } from '../types/task'

export function useBoard(projectId: string) {
  const { setBoard, moveTask, updateTask, assignWorker, setConnected } = useBoardStore()

  const query = useQuery({
    queryKey: ['board', projectId],
    queryFn: () => boardApi.get(projectId),
    enabled: !!projectId,
  })

  // Set board data when query completes
  useEffect(() => {
    if (query.data) {
      setBoard(query.data)
    }
  }, [query.data, setBoard])

  // WebSocket real-time updates
  const handleWsMessage = useCallback(
    (data: unknown) => {
      const event = data as {
        event: string
        task_id?: string
        task?: unknown
        from?: string
        to?: string
        worker_id?: string
      }
      switch (event.event) {
        case 'task_moved':
          if (event.task_id && event.from && event.to) {
            moveTask(event.task_id, event.from, event.to)
          }
          break
        case 'task_updated':
          if (event.task) {
            updateTask(event.task as Task)
          }
          break
        case 'worker_assigned':
          if (event.task_id && event.worker_id) {
            assignWorker(event.task_id, event.worker_id)
          }
          break
        case 'refresh':
          query.refetch()
          break
      }
    },
    [moveTask, updateTask, assignWorker, query]
  )

  const wsUrl = projectId
    ? `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/board/${projectId}`
    : ''

  useWebSocket({
    url: wsUrl,
    onMessage: handleWsMessage,
    onOpen: () => setConnected(true),
    onClose: () => setConnected(false),
    reconnect: true,
    autoConnect: !!projectId,
  })

  return { ...query, refetch: query.refetch }
}
