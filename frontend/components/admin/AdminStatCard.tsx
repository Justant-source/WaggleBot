import { cn } from '@/lib/utils'
import { TrendingUp, TrendingDown } from 'lucide-react'

interface Props {
  label: string
  value: string | number
  delta?: number
  deltaPositive?: boolean
  className?: string
}

export function AdminStatCard({ label, value, delta, deltaPositive, className }: Props) {
  return (
    <div className={cn('rounded-lg border border-gray-200 bg-white p-4 shadow-sm', className)}>
      <p className="text-xs font-medium uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-gray-900">{value}</p>
      {delta !== undefined && (
        <div className={cn('mt-1 flex items-center gap-1 text-xs', deltaPositive ? 'text-green-600' : 'text-red-600')}>
          {deltaPositive ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
          <span>{Math.abs(delta)}%</span>
        </div>
      )}
    </div>
  )
}
