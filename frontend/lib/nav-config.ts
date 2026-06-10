import {
  LayoutDashboard, Inbox, Pencil, Activity, Film, BarChart3, FlaskConical, Settings,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface NavItem {
  href: string
  label: string
  icon: LucideIcon
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    label: '운영',
    items: [
      { href: '/admin/overview',  label: '대시보드', icon: LayoutDashboard },
      { href: '/admin/inbox',     label: '수신함',   icon: Inbox },
      { href: '/admin/editor',    label: '편집실',   icon: Pencil },
      { href: '/admin/progress',  label: '진행현황', icon: Activity },
      { href: '/admin/gallery',   label: '갤러리',   icon: Film },
      { href: '/admin/analytics', label: '분석',     icon: BarChart3 },
      { href: '/admin/llm-logs',  label: 'LLM 이력', icon: FlaskConical },
      { href: '/admin/settings',  label: '설정',     icon: Settings },
    ],
  },
]
