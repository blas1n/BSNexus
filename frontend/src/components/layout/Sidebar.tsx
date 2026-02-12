import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Dashboard', icon: 'D' },
  { to: '/architect', label: 'Architect', icon: 'A' },
  { to: '/workers', label: 'Workers', icon: 'W' },
]

export default function Sidebar() {
  return (
    <aside className="w-56 bg-bg-surface border-r border-border min-h-[calc(100vh-3.25rem)]">
      <nav className="p-3 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-accent/10 text-accent-text'
                  : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'
              }`
            }
          >
            <span className="inline-flex items-center justify-center w-6 h-6 rounded bg-bg-hover text-xs font-bold text-text-secondary">
              {item.icon}
            </span>
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="absolute bottom-4 left-0 w-56 px-3">
        <div className="rounded-lg bg-bg-elevated px-3 py-2 text-xs text-text-tertiary">
          Settings (coming soon)
        </div>
      </div>
    </aside>
  )
}
