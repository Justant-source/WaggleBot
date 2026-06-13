'use client'
import { useEffect, useState } from 'react'
import { galleryApi } from '@/lib/api/gallery'
import { AdminSection } from '@/components/admin/AdminSection'
import { AdminPagination } from '@/components/admin/AdminPagination'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { toast } from 'sonner'
import { Film, Upload, Play, X } from 'lucide-react'

type GalleryItem = {
  post: { id: number; title: string; status: string }
  content?: {
    videoPath: string | null
    audioPath: string | null
    ttsVoice?: string | null
    variantLabel?: string | null
    uploadMeta?: { thumbnail_path?: string } | null
  }
}

function getMediaUrl(path: string): string {
  return `/media/${path.replace('/app/media/', '')}`
}

function getThumbnailUrl(item: GalleryItem): string | null {
  const tp = item.content?.uploadMeta?.thumbnail_path
  return tp ? getMediaUrl(tp) : null
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
              {/* 카드 프리뷰 — 썸네일 이미지(16:9) 우선, 없으면 비디오 */}
              <div
                className="relative flex h-32 items-center justify-center bg-gray-100 cursor-pointer group overflow-hidden"
                onClick={() => item.content?.videoPath && setPreviewItem(item)}
              >
                {(() => {
                  const thumbUrl = getThumbnailUrl(item)
                  if (thumbUrl) {
                    return (
                      <>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={thumbUrl}
                          alt={item.post.title}
                          className="h-full w-full object-cover pointer-events-none"
                        />
                        <div className="absolute inset-0 flex items-center justify-center bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity">
                          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/90">
                            <Play className="h-5 w-5 text-gray-800 ml-0.5" />
                          </div>
                        </div>
                      </>
                    )
                  }
                  if (item.content?.videoPath) {
                    return (
                      <>
                        <video
                          src={getMediaUrl(item.content.videoPath)}
                          className="h-full w-full object-contain pointer-events-none"
                          preload="metadata"
                        />
                        <div className="absolute inset-0 flex items-center justify-center bg-black/30 opacity-0 group-hover:opacity-100 transition-opacity">
                          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white/90">
                            <Play className="h-5 w-5 text-gray-800 ml-0.5" />
                          </div>
                        </div>
                      </>
                    )
                  }
                  return <Film className="h-8 w-8 text-gray-300" />
                })()}
              </div>

              <div className="p-3">
                <p className="text-sm font-medium text-gray-900 truncate">{item.post.title}</p>
                <div className="mt-1 flex flex-wrap items-center gap-1">
                  <Badge>{item.post.status}</Badge>
                  {item.content?.ttsVoice && (
                    <Badge variant="outline" className="bg-gray-50 text-gray-600 text-xs">
                      🎙 {item.content.ttsVoice}
                    </Badge>
                  )}
                  {item.content?.variantLabel && (
                    <Badge className="bg-blue-100 text-blue-700 border-blue-200 text-xs">
                      A/B {item.content.variantLabel}
                    </Badge>
                  )}
                </div>
                <div className="mt-2 flex gap-1">
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 text-xs flex-1"
                    onClick={() => galleryApi.hdRender(item.post.id).then(() => toast.info('HD 렌더링 요청')).catch(() => toast.error('HD 렌더 요청 실패'))}
                  >
                    HD 렌더
                  </Button>
                  <Button
                    size="sm"
                    className="h-7 text-xs flex-1"
                    onClick={() => galleryApi.upload(item.post.id).then(() => toast.info('업로드 요청')).catch(() => toast.error('업로드 요청 실패'))}
                  >
                    <Upload className="mr-1 h-3 w-3" /> 업로드
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </AdminSection>

      {total > 12 && (
        <AdminPagination
          page={page}
          totalPages={Math.ceil(total / 12)}
          onPageChange={(p) => { setPage(p); setPreviewItem(null) }}
        />
      )}

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
            <div className="flex gap-4 items-start">
              {previewItem.content?.videoPath && (
                <video
                  src={getMediaUrl(previewItem.content.videoPath)}
                  className="max-h-[85vh] rounded-lg shadow-2xl"
                  style={{ aspectRatio: '9/16' }}
                  controls
                  autoPlay
                />
              )}
              {/* YouTube 썸네일 미리보기 */}
              {getThumbnailUrl(previewItem) && (
                <div className="flex flex-col gap-2 pt-2">
                  <p className="text-xs text-white/50 uppercase tracking-wide">YouTube 썸네일</p>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={getThumbnailUrl(previewItem)!}
                    alt="YouTube 썸네일"
                    className="w-56 rounded-md shadow-xl border border-white/10"
                    style={{ aspectRatio: '16/9', objectFit: 'cover' }}
                  />
                </div>
              )}
            </div>

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
                onClick={() => galleryApi.hdRender(previewItem.post.id).then(() => toast.info('HD 렌더링 요청')).catch(() => toast.error('HD 렌더 요청 실패'))}
              >
                HD 렌더
              </Button>
              <Button
                size="sm"
                className="bg-blue-600 hover:bg-blue-700 text-white"
                onClick={() => galleryApi.upload(previewItem.post.id).then(() => toast.info('업로드 요청')).catch(() => toast.error('업로드 요청 실패'))}
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
