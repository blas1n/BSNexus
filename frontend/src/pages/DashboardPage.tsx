import { useQuery } from '@tanstack/react-query'
import { projectsApi } from '../api/projects'
import { Link, useNavigate } from 'react-router-dom'

const statusColors: Record<string, { bg: string; text: string }> = {
  design: { bg: 'bg-purple-100', text: 'text-purple-700' },
  active: { bg: 'bg-green-100', text: 'text-green-700' },
  paused: { bg: 'bg-yellow-100', text: 'text-yellow-700' },
  completed: { bg: 'bg-blue-100', text: 'text-blue-700' },
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const { data: projects, isLoading, error } = useQuery({
    queryKey: ['projects'],
    queryFn: projectsApi.list,
  })

  if (isLoading) {
    return <div className="text-gray-500">Loading projects...</div>
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Failed to load projects. Please try again.
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-900">Projects</h2>
        <button
          onClick={() => navigate('/architect')}
          className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          + New Project
        </button>
      </div>

      {projects?.length === 0 ? (
        <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center">
          <p className="text-gray-500 mb-4">No projects yet. Start by creating one with the Architect.</p>
          <button
            onClick={() => navigate('/architect')}
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Start with Architect
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects?.map((project) => {
            const colors = statusColors[project.status] || statusColors.design
            const phaseCount = project.phases.length

            return (
              <Link
                key={project.id}
                to={`/board/${project.id}`}
                className="block rounded-lg border border-gray-200 bg-white p-5 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between mb-3">
                  <h3 className="text-lg font-semibold text-gray-900">{project.name}</h3>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${colors.bg} ${colors.text}`}>
                    {project.status}
                  </span>
                </div>
                <p className="text-sm text-gray-500 mb-3 line-clamp-2">{project.description}</p>
                <div className="flex items-center justify-between text-xs text-gray-400">
                  <span>{phaseCount} phase{phaseCount !== 1 ? 's' : ''}</span>
                  <span>{new Date(project.updated_at).toLocaleDateString()}</span>
                </div>
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}
