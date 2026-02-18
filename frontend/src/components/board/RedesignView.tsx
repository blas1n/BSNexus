import { useState } from 'react'
import type { Task } from '../../types/task'
import { architectApi } from '../../api/architect'
import { Badge, Button } from '../common'

interface Props {
  tasks: Task[]
  onDone: () => void
}

export default function RedesignView({ tasks, onDone }: Props) {
  const [selectedId, setSelectedId] = useState<string>(tasks[0]?.id || '')
  const [editPrompt, setEditPrompt] = useState('')
  const [editTitle, setEditTitle] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [splitCount, setSplitCount] = useState(2)
  const [splitTasks, setSplitTasks] = useState<Array<{ title: string; worker_prompt: string }>>([])
  const [mode, setMode] = useState<'view' | 'modify' | 'split'>('view')

  const selected = tasks.find((t) => t.id === selectedId) || null

  const handleSelect = (task: Task) => {
    setSelectedId(task.id)
    setEditTitle(task.title)
    setEditPrompt(
      typeof task.worker_prompt === 'object' && task.worker_prompt
        ? String((task.worker_prompt as Record<string, unknown>).prompt || '')
        : ''
    )
    setMode('view')
  }

  const handleModify = async () => {
    if (!selected) return
    setIsSubmitting(true)
    try {
      await architectApi.redesignTask(selected.id, {
        action: 'modify',
        title: editTitle,
        worker_prompt: editPrompt,
      })
      onDone()
    } catch {
      // Error handling
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!selected) return
    setIsSubmitting(true)
    try {
      await architectApi.redesignTask(selected.id, { action: 'delete' })
      onDone()
    } catch {
      // Error handling
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleSplit = async () => {
    if (!selected || splitTasks.length === 0) return
    setIsSubmitting(true)
    try {
      await architectApi.redesignTask(selected.id, {
        action: 'split',
        split_tasks: splitTasks.map((st) => ({
          title: st.title,
          worker_prompt: st.worker_prompt,
          priority: selected.priority,
        })),
      })
      onDone()
    } catch {
      // Error handling
    } finally {
      setIsSubmitting(false)
    }
  }

  const initSplit = () => {
    setMode('split')
    setSplitTasks(
      Array.from({ length: splitCount }, (_, i) => ({
        title: `${selected?.title || 'Task'} (Part ${i + 1})`,
        worker_prompt: '',
      }))
    )
  }

  return (
    <div className="flex h-[calc(100vh-8rem)] bg-bg-primary">
      {/* Left panel: task list */}
      <div className="w-80 border-r border-border overflow-y-auto">
        <div className="p-4 border-b border-border">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-text-primary">Redesign Required</h2>
            <span className="text-xs text-text-tertiary">{tasks.length} task(s)</span>
          </div>
          <p className="text-xs text-text-secondary mt-1">
            These tasks exceeded max retries and need Architect intervention.
          </p>
        </div>
        <div className="p-2 space-y-1">
          {tasks.map((task) => (
            <button
              key={task.id}
              type="button"
              onClick={() => handleSelect(task)}
              className={`w-full text-left rounded-lg p-3 transition-colors ${
                selectedId === task.id
                  ? 'bg-bg-elevated border border-border'
                  : 'hover:bg-bg-hover'
              }`}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium text-text-primary truncate">{task.title}</span>
                <Badge color="redesign" label={`${task.retry_count}/${task.max_retries}`} size="sm" />
              </div>
              <p className="text-xs text-text-tertiary truncate">
                {task.error_message || 'No error details'}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* Right panel: detail + actions */}
      <div className="flex-1 overflow-y-auto">
        {selected ? (
          <div className="p-6 max-w-3xl">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-xl font-semibold text-text-primary">{selected.title}</h2>
                <div className="flex items-center gap-2 mt-1">
                  <Badge color="redesign" label="redesign" />
                  <Badge color={selected.priority} label={selected.priority} />
                  <span className="text-xs text-text-tertiary">
                    Retries: {selected.retry_count}/{selected.max_retries}
                  </span>
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={onDone}>
                Back to Board
              </Button>
            </div>

            {/* Error */}
            {selected.error_message && (
              <div
                className="mb-6 rounded-lg border p-4"
                style={{
                  backgroundColor: 'color-mix(in srgb, var(--status-redesign) 10%, transparent)',
                  borderColor: 'var(--status-redesign)',
                }}
              >
                <h3 className="text-sm font-medium mb-1" style={{ color: 'var(--status-redesign)' }}>
                  Failure Reason
                </h3>
                <p className="text-sm text-text-primary whitespace-pre-wrap">{selected.error_message}</p>
              </div>
            )}

            {/* Retry history */}
            {selected.qa_feedback_history && selected.qa_feedback_history.length > 0 && (
              <div className="mb-6">
                <h3 className="text-sm font-medium text-text-secondary mb-2">Retry History</h3>
                <div className="space-y-2 max-h-48 overflow-y-auto">
                  {selected.qa_feedback_history.map((entry, idx) => (
                    <div key={idx} className="rounded-lg bg-bg-elevated p-3 text-sm">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium text-text-primary">
                          Attempt {String(entry.attempt)}
                        </span>
                        <Badge
                          color={entry.type === 'qa_failure' ? 'review' : 'critical'}
                          label={String(entry.type === 'qa_failure' ? 'QA Fail' : 'Exec Fail')}
                          size="sm"
                        />
                      </div>
                      <p className="text-text-secondary">
                        {String(entry.feedback || entry.error || 'No details')}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Action buttons */}
            {mode === 'view' && (
              <div className="flex gap-3 mb-6">
                <Button
                  variant="primary"
                  size="md"
                  onClick={() => {
                    setEditTitle(selected.title)
                    setEditPrompt(
                      typeof selected.worker_prompt === 'object' && selected.worker_prompt
                        ? String((selected.worker_prompt as Record<string, unknown>).prompt || '')
                        : ''
                    )
                    setMode('modify')
                  }}
                >
                  Modify & Retry
                </Button>
                <Button variant="ghost" size="md" onClick={handleDelete} disabled={isSubmitting}>
                  Delete Task
                </Button>
                <Button variant="ghost" size="md" onClick={initSplit}>
                  Split into Tasks
                </Button>
              </div>
            )}

            {/* Modify form */}
            {mode === 'modify' && (
              <div className="mb-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-1">Title</label>
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="w-full rounded-lg border border-border bg-bg-input px-3 py-2 text-sm text-text-primary"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-1">Worker Prompt</label>
                  <textarea
                    value={editPrompt}
                    onChange={(e) => setEditPrompt(e.target.value)}
                    rows={10}
                    className="w-full rounded-lg border border-border bg-bg-input px-3 py-2 text-sm text-text-primary font-mono"
                  />
                </div>
                <div className="flex gap-3">
                  <Button variant="primary" size="md" onClick={handleModify} disabled={isSubmitting}>
                    {isSubmitting ? 'Saving...' : 'Save & Retry'}
                  </Button>
                  <Button variant="ghost" size="md" onClick={() => setMode('view')}>
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {/* Split form */}
            {mode === 'split' && (
              <div className="mb-6 space-y-4">
                <div className="flex items-center gap-3">
                  <label className="text-sm font-medium text-text-secondary">Number of sub-tasks:</label>
                  <input
                    type="number"
                    min={2}
                    max={10}
                    value={splitCount}
                    onChange={(e) => {
                      const n = parseInt(e.target.value, 10)
                      setSplitCount(n)
                      setSplitTasks(
                        Array.from({ length: n }, (_, i) => ({
                          title: splitTasks[i]?.title || `${selected.title} (Part ${i + 1})`,
                          worker_prompt: splitTasks[i]?.worker_prompt || '',
                        }))
                      )
                    }}
                    className="w-20 rounded-lg border border-border bg-bg-input px-2 py-1 text-sm text-text-primary"
                  />
                </div>
                {splitTasks.map((st, idx) => (
                  <div key={idx} className="rounded-lg border border-border p-4">
                    <h4 className="text-sm font-medium text-text-primary mb-2">Sub-task {idx + 1}</h4>
                    <input
                      type="text"
                      placeholder="Title"
                      value={st.title}
                      onChange={(e) => {
                        const updated = [...splitTasks]
                        updated[idx] = { ...updated[idx], title: e.target.value }
                        setSplitTasks(updated)
                      }}
                      className="w-full mb-2 rounded-lg border border-border bg-bg-input px-3 py-2 text-sm text-text-primary"
                    />
                    <textarea
                      placeholder="Worker prompt"
                      value={st.worker_prompt}
                      onChange={(e) => {
                        const updated = [...splitTasks]
                        updated[idx] = { ...updated[idx], worker_prompt: e.target.value }
                        setSplitTasks(updated)
                      }}
                      rows={4}
                      className="w-full rounded-lg border border-border bg-bg-input px-3 py-2 text-sm text-text-primary font-mono"
                    />
                  </div>
                ))}
                <div className="flex gap-3">
                  <Button variant="primary" size="md" onClick={handleSplit} disabled={isSubmitting}>
                    {isSubmitting ? 'Splitting...' : 'Confirm Split'}
                  </Button>
                  <Button variant="ghost" size="md" onClick={() => setMode('view')}>
                    Cancel
                  </Button>
                </div>
              </div>
            )}

            {/* Current prompt (read-only, shown in view mode) */}
            {mode === 'view' && selected.worker_prompt && (
              <div className="mb-6">
                <h3 className="text-sm font-medium text-text-secondary mb-2">Current Worker Prompt</h3>
                <pre className="rounded-lg bg-bg-elevated p-3 text-xs text-text-primary whitespace-pre-wrap font-mono max-h-48 overflow-y-auto">
                  {typeof selected.worker_prompt === 'object'
                    ? String((selected.worker_prompt as Record<string, unknown>).prompt || JSON.stringify(selected.worker_prompt, null, 2))
                    : String(selected.worker_prompt)}
                </pre>
              </div>
            )}
          </div>
        ) : (
          <div className="flex items-center justify-center h-full text-text-muted">
            Select a task from the left panel
          </div>
        )}
      </div>
    </div>
  )
}
