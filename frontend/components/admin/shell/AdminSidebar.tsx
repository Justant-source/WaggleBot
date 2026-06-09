'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { NAV_GROUPS } from '@/lib/nav-config'

interface Props {
  collapsed: boolean
  onToggle: () => void
}

export function AdminSidebar({ collapsed, onToggle }: Props) {
  const pathname = usePathname()

  const isActive = (href: string) => {
    if (href === '/admin') return pathname === '/admin'
    return pathname.startsWith(href)
  }

  return (
    <aside
      className={cn(
        'relative flex-shrink-0 flex flex-col bg-white border-r border-gray-200 h-full transition-all duration-200',
        collapsed ? 'w-16' : 'w-64',
      )}
    >
      {/* Toggle button */}
      <button
        onClick={onToggle}
        className="absolute -right-3 top-6 z-10 flex h-6 w-6 items-center justify-center rounded-full border border-gray-200 bg-white shadow-sm hover:bg-gray-50"
      >
        {collapsed ? (
          <ChevronRight className="h-3 w-3 text-gray-500" />
        ) : (
          <ChevronLeft className="h-3 w-3 text-gray-500" />
        )}
      </button>

      {/* Logo area */}
      <div className={cn('flex h-14 items-center border-b border-gray-200 px-4', collapsed && 'justify-center px-2')}>
        {!collapsed && (
          <span className="text-base font-semibold text-gray-900">WaggleBot</span>
        )}
        {collapsed && <span className="text-lg font-bold text-blue-600">W</span>}
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 px-2">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-4">
            {!collapsed && (
              <p className="mb-1 px-2 text-xs font-medium uppercase tracking-wider text-gray-400">
                {group.label}
              </p>
            )}
            <ul className="space-y-1">
              {group.items.map((item) => {
                const active = isActive(item.href)
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      className={cn(
                        'flex items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors',
                        active
                          ? 'bg-blue-50 text-blue-700 font-medium'
                          : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
                        collapsed && 'justify-center gap-0 px-0',
                      )}
                      title={collapsed ? item.label : undefined}
                    >
                      <item.icon className={cn('h-4 w-4 flex-shrink-0', active ? 'text-blue-600' : 'text-gray-500')} />
                      {!collapsed && <span>{item.label}</span>}
                    </Link>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>
    </aside>
  )
}
