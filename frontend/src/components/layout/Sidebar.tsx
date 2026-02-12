import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, Bot, Kanban, Users, Settings } from 'lucide-react'
import { SettingsModal } from './SettingsModal'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/architect', label: 'Architect', icon: Bot },
  { to: '/board', label: 'Board', icon: Kanban },
  { to: '/workers', label: 'Workers', icon: Users },
]

export default function Sidebar() {
  const location = useLocation()
  const [settingsOpen, setSettingsOpen] = useState(false)

  const isActive = (to: string) => {
    if (to === '/') return location.pathname === '/'
    return location.pathname.startsWith(to)
  }

  return (
    <aside className="w-[200px] bg-bg-surface border-r border-border h-screen flex flex-col">
      {/* Logo area */}
      <div className="p-4 mb-4">
        <div className="flex items-center gap-3">
          <div className="bg-accent w-8 h-8 rounded-full flex items-center justify-center">
            <span className="text-white text-sm font-bold">B</span>
          </div>
          <span className="text-text-primary text-sm font-semibold">BSNexus</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-1 px-3">
        {navItems.map((item) => {
          const Icon = item.icon
          const active = isActive(item.to)

          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === '/'}
              className={`flex items-center gap-3 px-3 py-2 text-sm font-medium transition-colors rounded-md ${
                active
                  ? 'bg-accent text-white'
                  : 'text-text-secondary hover:bg-bg-hover'
              }`}
            >
              <Icon size={18} />
              {item.label}
            </NavLink>
          )
        })}
      </nav>

      {/* Settings (pushed to bottom) */}
      <div className="mt-auto px-3 pb-4">
        <button
          type="button"
          onClick={() => setSettingsOpen(true)}
          className="flex items-center gap-3 px-3 py-2 text-sm text-text-secondary hover:bg-bg-hover rounded-md cursor-pointer transition-colors w-full"
        >
          <Settings size={18} />
          Settings
        </button>
      </div>

      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </aside>
  )
}
