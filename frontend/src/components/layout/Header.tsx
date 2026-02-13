import type { ReactNode } from 'react'

interface HeaderProps {
  title: string
  action?: ReactNode
}

export default function Header({ title, action }: HeaderProps) {
  return (
    <header className="bg-bg-primary border-b border-border px-8 py-4 flex items-center justify-between">
      <h1 className="text-xl font-semibold text-text-primary">{title}</h1>
      {action && <div className="flex items-center gap-3">{action}</div>}
    </header>
  )
}
