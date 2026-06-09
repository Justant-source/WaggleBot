'use client'
import { useEffect, useState } from 'react'
import { galleryApi } from '@/lib/api/gallery'
import { AdminSection } from '@/components/admin/AdminSection'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import { Film, Upload } from 'lucide-react'

export default function GalleryPage() {
  const [items, setItems] = useState<{ post: { id: number; title: string; status: string }; content?: { videoPath: string | null; audioPath: string | null } }[]>([])
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)

  useEffect(() => {
    galleryApi.list({ page, size: 12 }).then((res) => { setItems(res.items as typeof items); setTotal(res.total) })
  }, [page])

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-gray-900">갤러리</h1>
      <AdminSection title={`완료 ${total}건`}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <div key={item.post.id} className="rounded-lg border border-gray-200 bg-white overflow-hidden">
              <div className="flex h-32 items-center justify-center bg-gray-100">
                {item.content?.videoPath ? (
                  <video src={`/media/${item.content.videoPath.replace('/app/media/', '')}`} className="h-full w-full object-contain" controls />
                ) : (
                  <Film className="h-8 w-8 text-gray-300" />
                )}
              </div>
              <div className="p-3">
                <p className="text-sm font-medium text-gray-900 truncate">{item.post.title}</p>
                <Badge className="mt-1">{item.post.status}</Badge>
                <div className="mt-2 flex gap-1">
                  <Button size="sm" variant="outline" className="h-7 text-xs flex-1" onClick={() => { galleryApi.hdRender(item.post.id); toast.info('HD 렌더링 요청') }}>HD 렌더</Button>
                  <Button size="sm" className="h-7 text-xs flex-1" onClick={() => { galleryApi.upload(item.post.id); toast.info('업로드 요청') }}>
                    <Upload className="mr-1 h-3 w-3" /> 업로드
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </AdminSection>
    </div>
  )
}
