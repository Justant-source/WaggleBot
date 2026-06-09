import { ChevronLeft, ChevronRight } from 'lucide-react'

interface Props {
  page: number
  totalPages: number
  onPageChange: (page: number) => void
}

export function AdminPagination({ page, totalPages, onPageChange }: Props) {
  return (
    <div className="flex items-center justify-between border-t border-gray-200 pt-3 text-sm text-gray-500">
      <span>{page + 1} / {totalPages} 페이지</span>
      <div className="flex gap-1">
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page === 0}
          className="rounded-md p-1.5 hover:bg-gray-100 disabled:opacity-40"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages - 1}
          className="rounded-md p-1.5 hover:bg-gray-100 disabled:opacity-40"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
