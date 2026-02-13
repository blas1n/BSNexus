import { Badge } from './Badge'

interface StatCardProps {
  label: string
  value: string | number
  subtext?: string
  badge?: { color: string; label: string }
}

export function StatCard({ label, value, subtext, badge }: StatCardProps) {
  return (
    <div className="bg-bg-card border border-border rounded-lg p-6">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm text-text-secondary">{label}</span>
        {badge && <Badge color={badge.color} label={badge.label} />}
      </div>
      <div className="text-3xl font-bold text-text-primary">{value}</div>
      {subtext && (
        <div className="text-xs text-text-tertiary mt-1">{subtext}</div>
      )}
    </div>
  )
}

export type { StatCardProps }
