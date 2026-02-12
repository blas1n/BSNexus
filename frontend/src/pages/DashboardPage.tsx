import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { projectsApi } from '../api/projects'
import { Link, useNavigate } from 'react-router-dom'
import { Badge, Button, StatCard } from '../components/common'
import Header from '../components/layout/Header'

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

  const stats = useMemo(() => {
    const list = projects || []
    const totalProjects = list.length
    const completedProjects = list.filter(p => p.status === 'completed').length
    const activeProjects = list.filter(p => p.status === 'active').length
    const totalPhases = list.reduce((sum, p) => sum + (p.phases?.length || 0), 0)
    const completionRate = totalProjects > 0
      ? `${Math.round((completedProjects / totalProjects) * 100)}%`
      : '0%'
    return { totalProjects, completedProjects, activeProjects, totalPhases, completionRate }
  }, [projects])

  if (isLoading) {
    return (
      <>
        <Header title="Dashboard" />
        <div className="p-8 text-text-secondary">Loading projects...</div>
      </>
    )
  }

  if (error) {
    return (
      <>
        <Header title="Dashboard" />
        <div className="p-8">
          <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Failed to load projects. Please try again.
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <Header title="Dashboard" action={<Button size="sm" onClick={() => navigate('/architect')}>New Project</Button>} />
      <div className="p-8">
        {/* Stat Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          <StatCard
            label="Total Projects"
            value={stats.totalProjects}
            subtext={`${stats.completedProjects} completed`}
          />
          <StatCard
            label="Active Projects"
            value={stats.activeProjects}
            subtext={`${stats.totalPhases} phases total`}
          />
          <StatCard
            label="Workers Online"
            value="-"
            subtext="connect workers"
          />
          <StatCard
            label="Completion Rate"
            value={stats.completionRate}
            subtext={`${stats.completedProjects} of ${stats.totalProjects} projects`}
          />
        </div>

        {/* Project List */}
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
                  className="block rounded-lg border border-border bg-bg-card p-6 hover:border-accent/30 hover:shadow-md transition-all cursor-pointer"
                >
                  <div className="flex items-start justify-between mb-3">
                    <h3 className="text-lg font-semibold text-text-primary">{project.name}</h3>
                    <Badge color={badgeColor} label={project.status} />
                  </div>
                  <p className="text-sm text-text-secondary mt-1 mb-4 line-clamp-2">{project.description}</p>
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
    </>
  )
}
