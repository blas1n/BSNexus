import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { pmApi } from '../../api/pm'

interface Props {
  projectId: string
}

interface PMStatus {
  running: boolean
}

export default function PMControl({ projectId }: Props) {
  const queryClient = useQueryClient()
  const [logs, setLogs] = useState<string[]>([])

  const addLog = (message: string) => {
    setLogs((prev) => [message, ...prev].slice(0, 5))
  }

  const { data: status } = useQuery<PMStatus>({
    queryKey: ['pm-status', projectId],
    queryFn: () => pmApi.status(projectId),
    refetchInterval: 5000,
  })

  const startMutation = useMutation({
    mutationFn: () => pmApi.start(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pm-status', projectId] })
      addLog('PM started')
    },
    onError: () => addLog('Failed to start PM'),
  })

  const pauseMutation = useMutation({
    mutationFn: () => pmApi.pause(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pm-status', projectId] })
      addLog('PM paused')
    },
    onError: () => addLog('Failed to pause PM'),
  })

  const queueMutation = useMutation({
    mutationFn: () => pmApi.queueNext(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['board', projectId] })
      addLog('Queued next task')
    },
    onError: () => addLog('No tasks to queue'),
  })

  const isRunning = status?.running ?? false

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700">PM Control</h3>
        <div className="flex items-center gap-1.5">
          <span className={`inline-block w-2 h-2 rounded-full ${isRunning ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
          <span className="text-xs text-gray-500">{isRunning ? 'Running' : 'Paused'}</span>
        </div>
      </div>

      <div className="flex gap-2 mb-3">
        {isRunning ? (
          <button
            onClick={() => pauseMutation.mutate()}
            disabled={pauseMutation.isPending}
            className="flex-1 rounded-md bg-yellow-500 px-3 py-1.5 text-sm font-medium text-white hover:bg-yellow-600 disabled:opacity-50"
          >
            Pause
          </button>
        ) : (
          <button
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending}
            className="flex-1 rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            Start
          </button>
        )}
        <button
          onClick={() => queueMutation.mutate()}
          disabled={queueMutation.isPending}
          className="flex-1 rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          Queue Next
        </button>
      </div>

      {logs.length > 0 && (
        <div className="border-t border-gray-100 pt-2">
          <p className="text-xs font-medium text-gray-500 mb-1">Recent activity</p>
          <div className="space-y-0.5">
            {logs.map((log, i) => (
              <p key={i} className="text-xs text-gray-400">{log}</p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
