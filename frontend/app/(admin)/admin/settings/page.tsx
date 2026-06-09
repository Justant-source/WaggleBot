'use client'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { settingsApi } from '@/lib/api/settings'
import { AdminSection } from '@/components/admin/AdminSection'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { toast } from 'sonner'
import { Loader2, CheckCircle, XCircle } from 'lucide-react'

const schema = z.object({
  llm_model: z.enum(['haiku', 'sonnet']),
  tts_voice: z.string().min(1),
  auto_approve_threshold: z.coerce.number().min(0).max(100),
  max_chars_per_line: z.coerce.number().min(10).max(40),
})

type FormData = z.infer<typeof schema>

export default function SettingsPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [llmHealthStatus, setLlmHealthStatus] = useState<'unknown' | 'ok' | 'error'>('unknown')
  const [llmHealthChecking, setLlmHealthChecking] = useState(false)

  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { llm_model: 'haiku', tts_voice: 'yura', auto_approve_threshold: 80, max_chars_per_line: 20 },
  })

  const llmModel = watch('llm_model')

  useEffect(() => {
    settingsApi.get().then((cfg) => {
      if (cfg.llm_model === 'haiku' || cfg.llm_model === 'sonnet') setValue('llm_model', cfg.llm_model)
      if (cfg.tts_voice) setValue('tts_voice', String(cfg.tts_voice))
      if (cfg.auto_approve_threshold) setValue('auto_approve_threshold', Number(cfg.auto_approve_threshold))
      if (cfg.max_chars_per_line) setValue('max_chars_per_line', Number(cfg.max_chars_per_line))
      setLoading(false)
    })
  }, [])

  const onSubmit = async (data: FormData) => {
    setSaving(true)
    try { await settingsApi.save(data); toast.success('설정 저장됨') }
    catch { toast.error('저장 실패') }
    finally { setSaving(false) }
  }

  const checkLlmHealth = async () => {
    setLlmHealthChecking(true)
    try {
      const res = await fetch('/api/settings/health').catch(() => null)
      setLlmHealthStatus(res?.ok ? 'ok' : 'error')
    } catch { setLlmHealthStatus('error') }
    finally { setLlmHealthChecking(false) }
  }

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-gray-400" /></div>

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">설정</h1>
        <Button type="submit" disabled={saving}>
          {saving && <Loader2 className="mr-1 h-4 w-4 animate-spin" />} 저장
        </Button>
      </div>

      <AdminSection title="LLM 모델">
        <div className="max-w-sm space-y-4">
          <div>
            <Label className="mb-1 block">기본 모델</Label>
            <Select value={llmModel} onValueChange={(v) => setValue('llm_model', v as 'haiku' | 'sonnet')}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="haiku">Claude Haiku (빠름 · 저비용)</SelectItem>
                <SelectItem value="sonnet">Claude Sonnet (고품질 · 추천)</SelectItem>
              </SelectContent>
            </Select>
            <p className="mt-1 text-xs text-gray-400">대본생성/청킹은 항상 Sonnet 사용. 비디오프롬프트/번역은 Haiku 사용.</p>
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" size="sm" variant="outline" onClick={checkLlmHealth} disabled={llmHealthChecking}>
              {llmHealthChecking ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null} llm-worker 연결 확인
            </Button>
            {llmHealthStatus === 'ok' && <span className="flex items-center gap-1 text-xs text-green-600"><CheckCircle className="h-4 w-4" /> 정상</span>}
            {llmHealthStatus === 'error' && <span className="flex items-center gap-1 text-xs text-red-600"><XCircle className="h-4 w-4" /> 연결 실패</span>}
          </div>
        </div>
      </AdminSection>

      <AdminSection title="TTS">
        <div className="max-w-sm space-y-3">
          <div>
            <Label className="mb-1 block">목소리</Label>
            <Input {...register('tts_voice')} placeholder="yura" />
          </div>
        </div>
      </AdminSection>

      <AdminSection title="자동화">
        <div className="max-w-sm space-y-3">
          <div>
            <Label className="mb-1 block">자동 승인 임계값 (engagement score)</Label>
            <Input type="number" {...register('auto_approve_threshold')} />
          </div>
          <div>
            <Label className="mb-1 block">줄당 최대 글자 수</Label>
            <Input type="number" {...register('max_chars_per_line')} />
          </div>
        </div>
      </AdminSection>
    </form>
  )
}
