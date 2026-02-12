import { useQuery } from '@tanstack/react-query'
import { projectsApi } from '../api/projects'
import { Link, useNavigate } from 'react-router-dom'
import { Badge } from '../components/common'
import { Button } from '../components/common'

const statusBadgeColors: Record<string, string> = {
  design: '#8B5CF6',
  active: '#22C55E',
  paused: '#F59E0B',
  completed: '#3B82F6',
}

export default function DashboardPage() {
  const navigate = useNavigate()
  const { data: projects, isLoading, error } = useQuery({
    queryKey: ['projects'],
    queryFn: projectsApi.list,
  })

  if (isLoading) {
    return <div className="text-text-secondary">Loading projects...</div>
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
        <h2 className="text-2xl font-bold text-text-primary">Projects</h2>
        <Button onClick={() => navigate('/architect')}>
          + New Project
        </Button>
      </div>

      {projects?.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-12 text-center">
          <p className="text-text-secondary mb-4">No projects yet. Start by creating one with the Architect.</p>
          <Button onClick={() => navigate('/architect')}>
            Start with Architect
          </Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects?.map((project) => {
            const badgeColor = statusBadgeColors[project.status] || statusBadgeColors.design
            const phaseCount = project.phases.length

            return (
              <Link
                key={project.id}
                to={`/board/${project.id}`}
                className="block rounded-lg border border-border bg-bg-card p-5 hover:shadow-md transition-shadow"
              >
                <div className="flex items-start justify-between mb-3">
                  <h3 className="text-lg font-semibold text-text-primary">{project.name}</h3>
                  <Badge color={badgeColor} label={project.status} />
                </div>
                <p className="text-sm text-text-secondary mb-3 line-clamp-2">{project.description}</p>
                <div className="flex items-center justify-between text-xs text-text-tertiary">
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
