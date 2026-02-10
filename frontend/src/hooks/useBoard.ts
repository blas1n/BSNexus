import { useQuery } from '@tanstack/react-query'
import { boardApi } from '../api/board'
import { useBoardStore } from '../stores/boardStore'
import { useEffect } from 'react'

export function useBoard(projectId: string) {
  const { setTasks } = useBoardStore()

  const query = useQuery({
    queryKey: ['board', projectId],
    queryFn: () => boardApi.get(projectId),
    enabled: !!projectId,
    refetchInterval: 5000,
  })

  useEffect(() => {
    if (query.data) {
      const allTasks = Object.values(query.data.columns).flatMap((col) => col.tasks)
      setTasks(allTasks)
    }
  }, [query.data, setTasks])

  return query
}
