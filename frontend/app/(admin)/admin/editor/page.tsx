'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { editorApi } from '@/lib/api/editor'
import { AdminSection } from '@/components/admin/AdminSection'
import { AdminPagination } from '@/components/admin/AdminPagination'
import { Badge } from '@/components/ui/badge'
import type { Post } from '@/lib/types'
import { Loader2, Pencil } from 'lucide-react'

export default function EditorListPage() {
  const [posts, setPosts] = useState<Post[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    editorApi.list({ page, size: 20 }).then((res) => {
      setPosts(res.content); setTotal(res.totalElements)
    }).finally(() => setLoading(false))
  }, [page])

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-gray-900">편집실</h1>
      <AdminSection title={`대기 중 ${total}건`}>
        {loading ? (
          <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>
        ) : (
          <div className="space-y-2">
            {posts.map((post) => (
              <div key={post.id} className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3">
                <div>
                  <p className="font-medium text-gray-900">{post.title}</p>
                  <p className="text-xs text-gray-400">{post.siteCode} · {new Date(post.createdAt).toLocaleDateString('ko-KR')}</p>
                </div>
                <Link href={`/admin/editor/${post.id}`} className="inline-flex items-center gap-1 rounded-md bg-blue-50 px-3 py-1.5 text-sm text-blue-700 hover:bg-blue-100">
                  <Pencil className="h-3 w-3" /> 편집
                </Link>
              </div>
            ))}
            <AdminPagination page={page} totalPages={Math.ceil(total / 20)} onPageChange={setPage} />
          </div>
        )}
      </AdminSection>
    </div>
  )
}
