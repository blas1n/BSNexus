import { Link } from 'react-router-dom'

export default function Header() {
  return (
    <header className="bg-white border-b border-gray-200 px-6 py-3">
      <div className="flex items-center justify-between">
        <Link to="/" className="text-xl font-bold text-gray-900 hover:text-blue-600 transition-colors">
          BSNexus
        </Link>
        <nav className="flex items-center gap-4 text-sm text-gray-500">
          <span>Project Manager</span>
        </nav>
      </div>
    </header>
  )
}
