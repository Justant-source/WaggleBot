'use client'

import { useState, useEffect } from 'react'
import { AdminSidebar } from './AdminSidebar'
import { AdminTopBar } from './AdminTopBar'

interface Props {
  children: React.ReactNode
}

const SIDEBAR_KEY = 'wagglebot-sidebar-collapsed'

export function AdminShell({ children }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const stored = localStorage.getItem(SIDEBAR_KEY)
    if (stored !== null) setCollapsed(stored === 'true')
  }, [])

  const toggle = () => {
    setCollapsed((prev) => {
      const next = !prev
      localStorage.setItem(SIDEBAR_KEY, String(next))
      return next
    })
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      <AdminTopBar onMobileMenuToggle={() => setMobileOpen((v) => !v)} />
      <div className="flex flex-1 overflow-hidden pt-14">
        {/* Desktop sidebar */}
        <div className="hidden lg:flex">
          <AdminSidebar collapsed={collapsed} onToggle={toggle} />
        </div>
        {/* Mobile sidebar overlay */}
        {mobileOpen && (
          <div className="lg:hidden fixed inset-0 z-40" data-testid="mobile-sidebar-overlay">
            <div
              className="absolute inset-0 bg-black/40"
              onClick={() => setMobileOpen(false)}
            />
            <div className="absolute left-0 top-14 bottom-0 z-50">
              <AdminSidebar collapsed={false} onToggle={() => setMobileOpen(false)} />
            </div>
          </div>
        )}
        <main className="flex-1 overflow-auto bg-muted/40">
          <div className="p-6">{children}</div>
        </main>
      </div>
    </div>
  )
}
