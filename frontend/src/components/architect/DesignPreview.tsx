import type { Project } from '../../types/project'

interface Props {
  project: Project
  onConfirm?: () => void
}

export default function DesignPreview({ project, onConfirm }: Props) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">{project.name}</h3>
        <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
          {project.status}
        </span>
      </div>
      <p className="text-sm text-gray-600">{project.description}</p>

      {project.phases.map((phase) => (
        <div key={phase.id} className="border-t border-gray-100 pt-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-sm font-semibold text-gray-800">Phase {phase.order}: {phase.name}</span>
            <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{phase.status}</span>
          </div>
          {phase.description && (
            <p className="text-xs text-gray-500 mb-2">{phase.description}</p>
          )}
        </div>
      ))}

      {onConfirm && (
        <button
          onClick={onConfirm}
          className="w-full rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700"
        >
          Confirm Project Creation
        </button>
      )}
    </div>
  )
}
