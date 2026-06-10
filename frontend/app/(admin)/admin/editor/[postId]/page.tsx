'use client'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { editorApi } from '@/lib/api/editor'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { usePollingJob } from '@/lib/hooks/usePollingJob'
import { useEditorStore } from '@/lib/store/editorStore'
import { VoicePicker } from '@/components/editor/VoicePicker'
import { PromptPresetPanel } from '@/components/editor/PromptPresetPanel'
import { MoodGrid } from '@/components/editor/MoodGrid'
import type { Mood, ScriptData } from '@/lib/types'
import { Loader2, Save, CheckCircle, Play } from 'lucide-react'

const MAX_CHARS_DEFAULT = 60

export default function EditorDetailPage({ params }: { params: { postId: string } }) {
  const id = Number(params.postId)
  const [loading, setLoading] = useState(true)
  const [post, setPost] = useState<{ title: string } | null>(null)
  const [maxCharsPerLine, setMaxCharsPerLine] = useState(MAX_CHARS_DEFAULT)
  const [generateJobId, setGenerateJobId] = useState<number | null>(null)
  const [ttsJobId, setTtsJobId] = useState<number | null>(null)
  const [selectedVoice, setSelectedVoice] = useState<string | null>(null)
  const [genInstructions, setGenInstructions] = useState<string | null>(null)
  const [variantGroup, setVariantGroup] = useState<string | null>(null)
  const [variantLabel, setVariantLabel] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const { script, dirty, setScript, updateField, markClean } = useEditorStore()

  const genJob = usePollingJob(generateJobId, (jid) => editorApi.pollJob(jid))
  const ttsJob = usePollingJob(ttsJobId, (jid) => editorApi.pollJob(jid))

  useEffect(() => {
    editorApi.get(id).then((res) => {
      setPost({ title: res.post.title })
      if (res.script) setScript(res.script)
      setSelectedVoice(res.ttsVoice ?? null)
      setGenInstructions(res.genInstructions ?? null)
      setVariantGroup(res.variantGroup ?? null)
      setVariantLabel(res.variantLabel ?? null)
      if (res.maxCharsPerLine) setMaxCharsPerLine(res.maxCharsPerLine)
      setLoading(false)
    })
  }, [id])

  useEffect(() => {
    if (genJob.status === 'DONE') {
      const scriptJson = genJob.result?.script_json as string
      if (scriptJson) try { setScript(JSON.parse(scriptJson)) } catch {}
      toast.success('대본 생성 완료')
    }
    if (genJob.status === 'ERROR') toast.error('대본 생성 실패')
  }, [genJob.status])

  useEffect(() => {
    if (ttsJob.status === 'DONE') {
      const path = ttsJob.result?.preview_path as string
      if (path && audioRef.current) {
        const webPath = `/media/${path.replace('/app/media/', '')}?t=${Date.now()}`
        audioRef.current.src = webPath
        audioRef.current.play()
      }
      toast.success('TTS 미리듣기 준비 완료')
    }
    if (ttsJob.status === 'ERROR') toast.error('TTS 생성 실패')
  }, [ttsJob.status])

  const handleSave = async () => {
    if (!script) return
    try {
      await editorApi.saveScript(id, script)
      markClean(); toast.success('저장됨')
    } catch { toast.error('저장 실패') }
  }

  const handleGenerate = async (instructions: string) => {
    try {
      const res = await editorApi.generate(id, instructions ? { extra_instructions: instructions } : undefined)
      setGenerateJobId(res.jobId); toast.info('대본 생성 중...')
    } catch { toast.error('대본 생성 요청 실패') }
  }

  const handleTtsPreview = async () => {
    try {
      const res = await editorApi.ttsPreview(id, selectedVoice ? { voice: selectedVoice } : undefined)
      setTtsJobId(res.jobId); toast.info('TTS 생성 중...')
    } catch { toast.error('TTS 미리듣기 요청 실패') }
  }

  const handleConfirm = async () => {
    try {
      await editorApi.confirm(id)
      toast.success('확정됨 — APPROVED 상태로 전환')
    } catch { toast.error('확정 실패') }
  }

  const handleVoiceSelect = async (key: string | null) => {
    setSelectedVoice(key)
    try {
      await editorApi.setVoice(id, key)
      toast.success(key ? `보이스 "${key}" 저장됨` : '기본 보이스로 초기화됨')
    } catch {
      toast.error('보이스 저장 실패')
      setSelectedVoice(selectedVoice) // rollback
    }
  }

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>

  return (
    <div className="max-w-2xl">
      <div className="mb-2 flex items-center gap-2 flex-wrap">
        <h1 className="text-xl font-semibold text-gray-900">{post?.title}</h1>
        {variantGroup && variantLabel && (
          <Badge className="bg-blue-100 text-blue-800 border-blue-200">
            A/B {variantLabel}
          </Badge>
        )}
      </div>
      <div className="mb-4 flex gap-2 flex-wrap">
        <Button size="sm" variant="outline" onClick={handleTtsPreview} disabled={ttsJob.isPolling}>
          {ttsJob.isPolling ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Play className="mr-1 h-4 w-4" />} TTS 미리듣기
        </Button>
        <Button size="sm" variant="outline" onClick={handleSave} disabled={!dirty}>
          <Save className="mr-1 h-4 w-4" /> 저장
        </Button>
        <Button size="sm" onClick={handleConfirm}>
          <CheckCircle className="mr-1 h-4 w-4" /> 확정
        </Button>
      </div>
      <audio ref={audioRef} controls className="mb-4 w-full" />

      {/* 프롬프트 프리셋 패널 (AI 대본 재생성 포함) */}
      <div className="mb-4">
        <PromptPresetPanel
          postId={id}
          initialInstructions={genInstructions}
          onGenerate={handleGenerate}
          isGenerating={genJob.isPolling}
        />
      </div>

      {/* 보이스 피커 */}
      <div className="mb-4 rounded-lg border border-gray-200 bg-white p-4">
        <VoicePicker selectedVoice={selectedVoice} onSelect={handleVoiceSelect} />
      </div>

      {script && (
        <div className="space-y-3 rounded-lg border border-gray-200 bg-white p-4">
          <div>
            <label className="text-xs font-medium text-gray-500">Hook</label>
            <textarea
              className="mt-1 w-full rounded border border-gray-200 p-2 text-sm"
              rows={2}
              value={script.hook}
              onChange={(e) => updateField('hook', e.target.value)}
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-500">Body ({script.body.length}개 항목)</label>
            <div className="space-y-2">
              {script.body.map((item, idx) => {
                const lineLengths = item.lines.map((l) => l.length)
                const hasOverflow = lineLengths.some((len) => len > maxCharsPerLine)
                return (
                  <div key={idx} className="rounded border border-gray-200 p-2">
                    <div className="mb-1 flex items-center gap-2">
                      <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${item.type === 'comment' ? 'bg-purple-100 text-purple-700' : 'bg-blue-100 text-blue-700'}`}>
                        {item.type === 'comment' ? `댓글${item.author ? ` · ${item.author}` : ''}` : `본문 ${idx + 1}`}
                      </span>
                      {hasOverflow && (
                        <span className="text-xs text-red-500">글자수 초과</span>
                      )}
                    </div>
                    <textarea
                      className={`w-full rounded border p-1.5 text-xs leading-relaxed ${hasOverflow ? 'border-red-300 bg-red-50' : 'border-gray-100 bg-gray-50'}`}
                      rows={Math.max(2, item.lines.length)}
                      value={item.lines.join('\n')}
                      onChange={(e) => {
                        const newLines = e.target.value.split('\n')
                        const newBody = script.body.map((b, i) =>
                          i === idx ? { ...b, lines: newLines, lineCount: newLines.length } : b
                        )
                        updateField('body', newBody)
                      }}
                    />
                    {/* 줄별 글자수 카운터 */}
                    <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5">
                      {item.lines.map((line, li) => {
                        const len = line.length
                        const over = len > maxCharsPerLine
                        return (
                          <span key={li} className={`text-[10px] ${over ? 'text-red-500 font-semibold' : 'text-gray-400'}`}>
                            L{li + 1}:{len}{over ? `(+${len - maxCharsPerLine})` : ''}
                          </span>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div>
            <label className="text-xs font-medium text-gray-500">Closer</label>
            <textarea
              className="mt-1 w-full rounded border border-gray-200 p-2 text-sm"
              rows={2}
              value={script.closer}
              onChange={(e) => updateField('closer', e.target.value)}
            />
          </div>
          <div>
            <label className="mb-2 block text-xs font-medium text-gray-500">Mood</label>
            <MoodGrid
              value={script.mood}
              onChange={(mood) => updateField('mood', mood as Mood)}
            />
          </div>
        </div>
      )}
    </div>
  )
}
