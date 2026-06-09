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
      <AdminTopBar />
      <div className="flex flex-1 overflow-hidden pt-14">
        <div className="hidden lg:flex">
          <AdminSidebar collapsed={collapsed} onToggle={toggle} />
        </div>
        <main className="flex-1 overflow-auto bg-gray-50">
          <div className="p-6">{children}</div>
        </main>
      </div>
    </div>
  )
}
