import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { pmApi } from '../../api/pm'
import { Button, Badge } from '../common'

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
    <div className="rounded-lg border border-border bg-bg-surface p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-text-primary">PM Control</h3>
        {isRunning ? (
          <Badge color="in_progress" label="Running" />
        ) : (
          <Badge color="waiting" label="Paused" />
        )}
      </div>

      <div className="flex gap-2 mb-3">
        {isRunning ? (
          <Button
            variant="secondary"
            onClick={() => pauseMutation.mutate()}
            disabled={pauseMutation.isPending}
            size="sm"
            className="flex-1"
          >
            Pause
          </Button>
        ) : (
          <Button
            variant="secondary"
            onClick={() => startMutation.mutate()}
            disabled={startMutation.isPending}
            size="sm"
            className="flex-1"
          >
            Start
          </Button>
        )}
        <Button
          variant="primary"
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
          <div className="bg-bg-elevated rounded-md p-3 space-y-0.5">
            {logs.map((log, i) => (
              <p key={i} className="text-xs text-text-secondary">{log}</p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
