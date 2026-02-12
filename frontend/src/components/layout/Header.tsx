import { Link } from 'react-router-dom'

export default function Header() {
  return (
    <header className="bg-bg-primary border-b border-border px-6 py-3">
      <div className="flex items-center justify-between">
        <Link to="/" className="text-xl font-bold text-text-primary hover:text-accent-text transition-colors">
          BSNexus
        </Link>
        <nav className="flex items-center gap-4 text-sm text-text-secondary">
          <span>Project Manager</span>
        </nav>
      </div>
    </header>
  )
}
