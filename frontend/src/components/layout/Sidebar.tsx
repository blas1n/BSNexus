import { NavLink } from 'react-router-dom'

const navItems = [
  { to: '/', label: 'Dashboard', icon: 'D' },
  { to: '/architect', label: 'Architect', icon: 'A' },
  { to: '/workers', label: 'Workers', icon: 'W' },
]

export default function Sidebar() {
  return (
    <aside className="w-56 bg-gray-50 border-r border-gray-200 min-h-[calc(100vh-3.25rem)]">
      <nav className="p-3 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-blue-50 text-blue-700'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
              }`
            }
          >
            <span className="inline-flex items-center justify-center w-6 h-6 rounded bg-gray-200 text-xs font-bold text-gray-600">
              {item.icon}
            </span>
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="absolute bottom-4 left-0 w-56 px-3">
        <div className="rounded-lg bg-gray-100 px-3 py-2 text-xs text-gray-400">
          Settings (coming soon)
        </div>
      </div>
    </aside>
  )
}
