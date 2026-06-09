'use client'

import { Menu, Moon, Sun } from 'lucide-react'
import { useTheme } from 'next-themes'
import { cn } from '@/lib/utils'

interface Props {
  onMobileMenuToggle?: () => void
}

export function AdminTopBar({ onMobileMenuToggle }: Props) {
  const { theme, setTheme } = useTheme()

  return (
    <header className="fixed top-0 left-0 right-0 z-10 flex h-14 items-center justify-between border-b border-gray-200 bg-white px-4 shadow-sm">
      <div className="flex items-center gap-3">
        <button
          className="lg:hidden rounded-md p-1.5 text-gray-500 hover:bg-gray-100"
          onClick={onMobileMenuToggle}
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="text-base font-semibold text-gray-800 lg:hidden">WaggleBot</span>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
          className="rounded-md p-1.5 text-gray-500 hover:bg-gray-100"
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </button>
      </div>
    </header>
  )
}
