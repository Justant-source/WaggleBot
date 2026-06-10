'use client'

const MOODS = [
  { key: 'humor',       emoji: '😄', label: '유머' },
  { key: 'touching',    emoji: '🥺', label: '감동' },
  { key: 'anger',       emoji: '😤', label: '공분' },
  { key: 'sadness',     emoji: '😢', label: '슬픔' },
  { key: 'horror',      emoji: '😱', label: '공포' },
  { key: 'info',        emoji: '💡', label: '정보' },
  { key: 'controversy', emoji: '🔥', label: '논란' },
  { key: 'daily',       emoji: '📅', label: '일상' },
  { key: 'shock',       emoji: '💥', label: '충격' },
]

interface Props {
  value: string
  onChange: (mood: string) => void
}

export function MoodGrid({ value, onChange }: Props) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {MOODS.map((mood) => {
        const isSelected = value === mood.key
        return (
          <button
            key={mood.key}
            type="button"
            onClick={() => onChange(mood.key)}
            className={`flex flex-col items-center rounded-lg px-2 py-3 text-sm font-medium transition-colors ${
              isSelected
                ? 'bg-primary text-primary-foreground shadow-sm'
                : 'bg-muted hover:bg-muted/80 text-gray-700'
            }`}
          >
            <span className="text-lg leading-none">{mood.emoji}</span>
            <span className="mt-1 text-xs">{mood.label}</span>
          </button>
        )
      })}
    </div>
  )
}
