import { useQuery } from '@tanstack/react-query'
import { projectsApi } from '../api/projects'
import { Link } from 'react-router-dom'

export default function DashboardPage() {
  const { data: projects, isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: projectsApi.list,
  })

  if (isLoading) return <div className="text-gray-500">Loading...</div>

  return (
    <div>
      <h2 className="text-2xl font-bold text-gray-900 mb-6">Projects</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {projects?.map((project) => (
          <Link
            key={project.id}
            to={`/board/${project.id}`}
            className="block rounded-lg border border-gray-200 bg-white p-4 hover:shadow-md transition-shadow"
          >
            <h3 className="text-lg font-semibold text-gray-900">{project.name}</h3>
            <p className="text-sm text-gray-500 mt-1">{project.description}</p>
            <span className="mt-2 inline-block rounded-full bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
              {project.status}
            </span>
          </Link>
        ))}
      </div>
    </div>
  )
}
