import { AdminShell } from '@/components/admin/shell/AdminShell'

// 관리자 대시보드는 정적 캐시 금지. 기본값으로 두면 Next.js가 라우트를
// Cache-Control: s-maxage=31536000(1년)로 캐시해, 프론트 재배포 후에도
// 브라우저가 옛 번들을 계속 로드한다(승인 버튼 등 스테일 동작 유발).
// force-dynamic → 매 요청 동적 렌더 + Cache-Control: no-store.
export const dynamic = 'force-dynamic'

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminShell>{children}</AdminShell>
}
