import type { Project } from '../../types/project'
import { Badge, Button } from '../common'

const statusBadgeColors: Record<string, string> = {
  design: '#8B5CF6',
  active: '#22C55E',
  paused: '#F59E0B',
  completed: '#3B82F6',
}

interface Props {
  project: Project
  onConfirm?: () => void
}

export default function DesignPreview({ project, onConfirm }: Props) {
  const badgeColor = statusBadgeColors[project.status] || statusBadgeColors.design

  return (
    <div className="rounded-lg border border-border bg-bg-card p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-text-primary">{project.name}</h3>
        <Badge color={badgeColor} label={project.status} />
      </div>
      <p className="text-sm text-text-secondary">{project.description}</p>

      {project.phases.map((phase) => (
        <div key={phase.id} className="border-t border-border-subtle pt-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-semibold text-text-primary">Phase {phase.order}: {phase.name}</span>
            <Badge color="#6B7280" label={phase.status} />
          </div>
          {phase.description && (
            <p className="text-xs text-text-secondary mb-2">{phase.description}</p>
          )}
        </div>
      ))}

      {onConfirm && (
        <Button
          onClick={onConfirm}
          className="w-full bg-green-600 hover:bg-green-700"
        >
          Confirm Project Creation
        </Button>
      )}
    </div>
  )
}
