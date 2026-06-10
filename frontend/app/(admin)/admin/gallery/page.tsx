'use client'
import { useEffect, useState } from 'react'
import { galleryApi } from '@/lib/api/gallery'
import { AdminSection } from '@/components/admin/AdminSection'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import { Film, Upload, Play, X } from 'lucide-react'

type GalleryItem = {
  post: { id: number; title: string; status: string }
  content?: { videoPath: string | null; audioPath: string | null }
}

function getVideoUrl(videoPath: string): string {
  return `/media/${videoPath.replace('/app/media/', '')}`
}

export default function GalleryPage() {
  const [items, setItems] = useState<GalleryItem[]>([])
  const [page, setPage] = useState(0)
  const [total, setTotal] = useState(0)
  const [previewItem, setPreviewItem] = useState<GalleryItem | null>(null)

  useEffect(() => {
    galleryApi.list({ page, size: 12 }).then((res) => {
      setItems(res.items as GalleryItem[])
      setTotal(res.total)
    })
  }, [page])

  // Esc 키로 모달 닫기
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setPreviewItem(null)
    }
    if (previewItem) window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [previewItem])

  return (
    <div>
      <h1 className="mb-6 text-xl font-semibold text-gray-900">갤러리</h1>
      <AdminSection title={`완료 ${total}건`}>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((item) => (
            <div key={item.post.id} className="rounded-lg border border-gray-200 bg-white overflow-hidden">
              {/* 썸네일 영역 — 클릭 시 풀스크린 모달 오픈 */}
              <div
                className="relative flex h-32 items-center justify-center bg-gray-100 cursor-pointer group"
                onClick={() => item.content?.videoPath && setPreviewItem(item)}
              >
                {item.content?.videoPath ? (
                  <>
                    <video
                      src={getVideoUrl(item.content.videoPath)}
                      className="h-full w-full object-contain pointer-events-none"
                      preload="metadata"
                    />
                    {/* 재생 버튼 오버레이 */}
                    <div className="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity">
                      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/90">
                        <Play className="h-5 w-5 text-gray-800 ml-0.5" />
                      </div>
                    </div>
                  </>
                ) : (
                  <Film className="h-8 w-8 text-gray-300" />
                )}
              </div>

              <div className="p-3">
                <p className="text-sm font-medium text-gray-900 truncate">{item.post.title}</p>
                <Badge className="mt-1">{item.post.status}</Badge>
                <div className="mt-2 flex gap-1">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs flex-1"
                    onClick={() => { galleryApi.hdRender(item.post.id); toast.info('HD 렌더링 요청') }}
                  >
                    HD 렌더
                  </Button>
                  <Button
                    size="sm"
                    className="h-7 text-xs flex-1"
                    onClick={() => { galleryApi.upload(item.post.id); toast.info('업로드 요청') }}
                  >
                    <Upload className="mr-1 h-3 w-3" /> 업로드
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </AdminSection>

      {/* 풀스크린 비디오 프리뷰 모달 */}
      {previewItem && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
          onClick={() => setPreviewItem(null)}
        >
          <div
            className="relative flex flex-col items-center gap-4"
            onClick={(e) => e.stopPropagation()}
          >
            {/* 닫기 버튼 (우상단) */}
            <button
              className="absolute -top-10 right-0 flex h-8 w-8 items-center justify-center rounded-full bg-white/20 text-white hover:bg-white/30 transition-colors"
              onClick={() => setPreviewItem(null)}
            >
              <X className="h-4 w-4" />
            </button>

            {/* 9:16 비율 비디오 */}
            {previewItem.content?.videoPath && (
              <video
                src={getVideoUrl(previewItem.content.videoPath)}
                className="max-h-[85vh] rounded-lg shadow-2xl"
                style={{ aspectRatio: '9/16' }}
                controls
                autoPlay
              />
            )}

            {/* 제목 + 상태 */}
            <p className="max-w-xs text-center text-sm font-medium text-white/90 truncate">
              {previewItem.post.title}
            </p>

            {/* 액션 버튼 */}
            <div className="flex gap-3">
              <Button
                size="sm"
                variant="outline"
                className="bg-white/10 text-white border-white/30 hover:bg-white/20"
                onClick={() => { galleryApi.hdRender(previewItem.post.id); toast.info('HD 렌더링 요청') }}
              >
                HD 렌더
              </Button>
              <Button
                size="sm"
                className="bg-blue-600 hover:bg-blue-700 text-white"
                onClick={() => { galleryApi.upload(previewItem.post.id); toast.info('업로드 요청') }}
              >
                <Upload className="mr-1 h-3 w-3" /> 업로드
              </Button>
              <Button
                size="sm"
                variant="outline"
                className="bg-white/10 text-white border-white/30 hover:bg-white/20"
                onClick={() => setPreviewItem(null)}
              >
                닫기
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
