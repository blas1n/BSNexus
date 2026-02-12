import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { pmApi } from '../../api/pm'
import { Button } from '../common'

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
    <div className="rounded-lg border border-border bg-bg-card p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary">PM Control</h3>
        <div className="flex items-center gap-1.5">
          <span className={`inline-block w-2 h-2 rounded-full ${isRunning ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
          <span className="text-xs text-text-secondary">{isRunning ? 'Running' : 'Paused'}</span>
        </div>
      </div>

      <div className="flex gap-2 mb-3">
        {isRunning ? (
          <Button
            onClick={() => pauseMutation.mutate()}
            disabled={pauseMutation.isPending}
            size="sm"
            className="flex-1 bg-yellow-500 hover:bg-yellow-600"
          >
            Pause
          </Button>
        ) : (
          <Button
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending}
            size="sm"
            className="flex-1 bg-green-600 hover:bg-green-700"
          >
            Start
          </Button>
        )}
        <Button
          onClick={() => queueMutation.mutate()}
          disabled={queueMutation.isPending}
          size="sm"
          className="flex-1"
        >
          Queue Next
        </Button>
      </div>

      {logs.length > 0 && (
        <div className="border-t border-border-subtle pt-2">
          <p className="text-xs font-medium text-text-secondary mb-1">Recent activity</p>
          <div className="space-y-0.5">
            {logs.map((log, i) => (
              <p key={i} className="text-xs text-text-tertiary">{log}</p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
