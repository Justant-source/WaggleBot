'use client'

import { useEffect, useRef, useState } from 'react'
import { ttsApi } from '@/lib/api/tts'
import { Play, Square } from 'lucide-react'
import type { VoiceInfo } from '@/lib/types'

interface Props {
  selectedVoice: string | null
  onSelect: (key: string | null) => void
}

export function VoicePicker({ selectedVoice, onSelect }: Props) {
  const [voices, setVoices] = useState<VoiceInfo[]>([])
  const [hiddenSamples, setHiddenSamples] = useState<Set<string>>(new Set())
  const [playingKey, setPlayingKey] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    ttsApi.voices().then((res) => setVoices(res.voices)).catch(() => {})
  }, [])

  const handlePlay = (voice: VoiceInfo, e: React.MouseEvent) => {
    e.stopPropagation()
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    if (playingKey === voice.key) {
      setPlayingKey(null)
      return
    }
    const audio = new Audio(voice.sampleUrl)
    audio.onended = () => setPlayingKey(null)
    audio.onerror = () => {
      setHiddenSamples((prev) => new Set([...prev, voice.key]))
      setPlayingKey(null)
    }
    audioRef.current = audio
    audio.play()
    setPlayingKey(voice.key)
  }

  // Cleanup on unmount
  useEffect(() => {
    return () => { audioRef.current?.pause() }
  }, [])

  const allCards: Array<{ key: string | null; label: string; sampleUrl?: string }> = [
    { key: null, label: '전역 기본값 사용' },
    ...voices.map((v) => ({ key: v.key, label: v.label, sampleUrl: v.sampleUrl })),
  ]

  return (
    <div>
      <p className="mb-2 text-xs font-medium text-gray-500">TTS 보이스 선택</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {allCards.map((card) => {
          const isSelected = selectedVoice === card.key
          const isHidden = card.key !== null && hiddenSamples.has(card.key)
          const isPlaying = card.key !== null && playingKey === card.key
          return (
            <div
              key={card.key ?? '__default__'}
              onClick={() => onSelect(card.key)}
              className={`cursor-pointer rounded-lg border p-3 text-center transition-all ${
                isSelected
                  ? 'ring-2 ring-primary border-primary bg-primary/5'
                  : 'border-gray-200 bg-white hover:bg-gray-50'
              }`}
            >
              <p className="text-xs font-medium text-gray-800 truncate">{card.label}</p>
              {card.sampleUrl && !isHidden && card.key !== null && (
                <button
                  className="mt-1.5 flex items-center justify-center gap-1 rounded px-2 py-0.5 text-xs text-gray-500 hover:bg-gray-100 mx-auto"
                  onClick={(e) => {
                    const voice = voices.find((v) => v.key === card.key)
                    if (voice) handlePlay(voice, e)
                  }}
                  title="샘플 재생"
                >
                  {isPlaying
                    ? <><Square className="h-3 w-3" />정지</>
                    : <><Play className="h-3 w-3" />재생</>
                  }
                </button>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
