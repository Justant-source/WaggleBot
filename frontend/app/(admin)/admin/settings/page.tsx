'use client'
import { useEffect, useState } from 'react'
import { useForm, Controller } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { settingsApi } from '@/lib/api/settings'
import { ttsApi } from '@/lib/api/tts'
import type { VoiceInfo } from '@/lib/types'
import { AdminSection } from '@/components/admin/AdminSection'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Switch } from '@/components/ui/switch'
import { toast } from 'sonner'
import { Loader2, CheckCircle, XCircle, KeyRound, Link2 } from 'lucide-react'

const schema = z.object({
  llm_backend: z.enum(['cli', 'api']),
  llm_api_base_url: z.string().trim().url('올바른 URL을 입력하세요 (.../v1)').or(z.literal('')),
  llm_model: z.enum(['haiku', 'sonnet']),
  llm_model_overrides: z.string(),
  llm_prompt_cache: z.boolean(),
  use_content_processor: z.boolean(),
  tts_voice: z.string().min(1),
  auto_approve_enabled: z.boolean(),
  auto_approve_threshold: z.coerce.number().min(0).max(100),
  auto_upload: z.boolean(),
  upload_privacy: z.enum(['public', 'unlisted', 'private']),
  max_chars_per_line: z.coerce.number().min(10).max(40),
})

const DEFAULT_BASE_URL = 'https://api.anthropic.com/v1'

type FormData = z.infer<typeof schema>

export default function SettingsPage() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [llmHealthStatus, setLlmHealthStatus] = useState<'unknown' | 'ok' | 'error'>('unknown')
  const [llmHealthChecking, setLlmHealthChecking] = useState(false)

  const [voices, setVoices] = useState<VoiceInfo[]>([])
  const [apiKey, setApiKey] = useState('')
  const [apiKeyMasked, setApiKeyMasked] = useState<string | null>(null)
  const [savingKey, setSavingKey] = useState(false)

  const { register, handleSubmit, setValue, watch, control, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      llm_backend: 'cli',
      llm_api_base_url: DEFAULT_BASE_URL,
      llm_model: 'haiku',
      llm_model_overrides: '{}',
      llm_prompt_cache: true,
      use_content_processor: false,
      tts_voice: 'yura',
      auto_approve_enabled: false,
      auto_approve_threshold: 80,
      auto_upload: false,
      upload_privacy: 'unlisted',
      max_chars_per_line: 20,
    },
  })

  const llmBackend = watch('llm_backend')
  const llmModel = watch('llm_model')
  const ttsVoice = watch('tts_voice')
  const autoApproveEnabled = watch('auto_approve_enabled')
  const autoUpload = watch('auto_upload')


  useEffect(() => {
    settingsApi.get().then((cfg) => {
      if (cfg.llm_backend === 'cli' || cfg.llm_backend === 'api') setValue('llm_backend', cfg.llm_backend)
      if (cfg.llm_api_base_url) setValue('llm_api_base_url', String(cfg.llm_api_base_url))
      if (cfg.llm_model === 'haiku' || cfg.llm_model === 'sonnet') setValue('llm_model', cfg.llm_model)
      if (cfg.llm_model_overrides) setValue('llm_model_overrides', String(cfg.llm_model_overrides))
      setValue('llm_prompt_cache', cfg.llm_prompt_cache !== 'false' && cfg.llm_prompt_cache !== false)
      setValue('use_content_processor', cfg.use_content_processor === 'true' || cfg.use_content_processor === true)
      if (cfg.tts_voice) setValue('tts_voice', String(cfg.tts_voice))
      setValue('auto_approve_enabled', cfg.auto_approve_enabled === 'true' || cfg.auto_approve_enabled === true)
      if (cfg.auto_approve_threshold) setValue('auto_approve_threshold', Number(cfg.auto_approve_threshold))
      setValue('auto_upload', cfg.auto_upload === 'true' || cfg.auto_upload === true)
      if (cfg.upload_privacy === 'public' || cfg.upload_privacy === 'unlisted' || cfg.upload_privacy === 'private')
        setValue('upload_privacy', cfg.upload_privacy)
      if (cfg.max_chars_per_line) setValue('max_chars_per_line', Number(cfg.max_chars_per_line))
      setLoading(false)
    })
    settingsApi.getCredentials().then((creds) => {
      const v = creds?.anthropic_api_key
      if (typeof v === 'string' && v.length > 0) setApiKeyMasked(v)
    }).catch(() => {})
    ttsApi.voices().then((res) => setVoices(res.voices)).catch(() => {})
  }, [])

  const onSubmit = async (data: FormData) => {
    setSaving(true)
    try {
      await settingsApi.save({
        ...data,
        auto_approve_enabled: String(data.auto_approve_enabled),
        auto_upload: String(data.auto_upload),
        llm_prompt_cache: String(data.llm_prompt_cache),
        use_content_processor: String(data.use_content_processor),
      })
      toast.success('설정 저장됨')
    } catch { toast.error('저장 실패') }
    finally { setSaving(false) }
  }

  const saveApiKey = async () => {
    if (!apiKey.trim()) { toast.error('API 키를 입력하세요'); return }
    setSavingKey(true)
    try {
      await settingsApi.saveCredentials({ anthropic_api_key: apiKey.trim() })
      toast.success('API 키 저장됨 (config/credentials.json)')
      setApiKeyMasked(apiKey.trim().slice(0, 2) + '***')
      setApiKey('')
    } catch { toast.error('API 키 저장 실패') }
    finally { setSavingKey(false) }
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

      <AdminSection title="AI 대본 생성 백엔드">
        <div className="max-w-xl space-y-4">
          <div>
            <Label className="mb-1 block">LLM 호출 방식</Label>
            <Select value={llmBackend} onValueChange={(v) => setValue('llm_backend', v as 'cli' | 'api')}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="cli">Claude CLI 브릿지 (llm-worker · 구독)</SelectItem>
                <SelectItem value="api">Claude API (Anthropic API 키 · 종량제)</SelectItem>
              </SelectContent>
            </Select>
            <p className="mt-1 text-xs text-gray-400">
              CLI 브릿지는 Claude 구독(llm-worker)을 사용합니다. 한도 소진 시 <b>Claude API</b>로 전환하세요.
            </p>
          </div>

          {llmBackend === 'api' && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
              <div className="mb-4">
                <Label className="mb-1 flex items-center gap-1.5 text-amber-900">
                  <Link2 className="h-4 w-4" /> API Base URL
                </Label>
                <Input {...register('llm_api_base_url')} placeholder={DEFAULT_BASE_URL} autoComplete="off" spellCheck={false} />
                {errors.llm_api_base_url && <p className="mt-1 text-xs text-red-600">{errors.llm_api_base_url.message}</p>}
                <p className="mt-1 text-xs text-amber-800">
                  공식 Anthropic: <code className="rounded bg-amber-100 px-1">{DEFAULT_BASE_URL}</code>.
                  프록시 사용 시 <code className="rounded bg-amber-100 px-1">.../v1</code> 형태 입력.
                </p>
              </div>
              <Label className="mb-1 flex items-center gap-1.5 text-amber-900">
                <KeyRound className="h-4 w-4" /> Anthropic API 키
              </Label>
              <div className="flex gap-2">
                <Input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={apiKeyMasked ? `저장됨 (${apiKeyMasked}) — 변경 시 새 키 입력` : 'sk-ant-...'}
                  autoComplete="off"
                />
                <Button type="button" onClick={saveApiKey} disabled={savingKey}>
                  {savingKey && <Loader2 className="mr-1 h-4 w-4 animate-spin" />} 키 저장
                </Button>
              </div>
              {apiKeyMasked && <p className="mt-1 text-xs font-medium text-green-700">현재 키 설정됨 ✓</p>}
            </div>
          )}
        </div>
      </AdminSection>

      <AdminSection title="LLM 모델">
        <div className="max-w-sm space-y-4">
          <div>
            <Label className="mb-1 block">기본 모델</Label>
            <Select value={llmModel} onValueChange={(v) => setValue('llm_model', v as 'haiku' | 'sonnet')}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="haiku">Claude Haiku (빠름 · 저비용)</SelectItem>
                <SelectItem value="sonnet">Claude Sonnet (고품질 · 추천)</SelectItem>
              </SelectContent>
            </Select>
            <p className="mt-1 text-xs text-gray-400">대본생성/청킹은 항상 Sonnet. 비디오프롬프트/번역은 Haiku.</p>
          </div>
          <div>
            <Label className="mb-1 block">모델 오버라이드 (JSON)</Label>
            <textarea
              {...register('llm_model_overrides')}
              rows={3}
              className="w-full rounded-md border border-gray-300 px-3 py-2 font-mono text-xs shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder='{"chunk": "sonnet", "video_prompt": "haiku"}'
              spellCheck={false}
            />
            <p className="mt-1 text-xs text-gray-400">callType별 모델 강제 지정. 비워두면 기본 모델 사용.</p>
          </div>
          {llmBackend === 'api' && (
            <div className="flex items-center justify-between rounded-lg border border-gray-200 p-3">
              <div>
                <p className="text-sm font-medium text-gray-800">프롬프트 캐싱</p>
                <p className="text-xs text-gray-400">Anthropic API 프롬프트 캐시 활성화 — 비용 절감</p>
              </div>
              <Controller
                name="llm_prompt_cache"
                control={control}
                render={({ field }) => (
                  <Switch
                    id="llm_prompt_cache"
                    checked={field.value}
                    onChange={(e) => field.onChange(e.target.checked)}
                  />
                )}
              />
            </div>
          )}
          <div className="flex items-center gap-2">
            <Button type="button" size="sm" variant="outline" onClick={checkLlmHealth} disabled={llmHealthChecking}>
              {llmHealthChecking && <Loader2 className="mr-1 h-4 w-4 animate-spin" />} llm-worker 연결 확인
            </Button>
            {llmHealthStatus === 'ok' && <span className="flex items-center gap-1 text-xs text-green-600"><CheckCircle className="h-4 w-4" /> 정상</span>}
            {llmHealthStatus === 'error' && <span className="flex items-center gap-1 text-xs text-red-600"><XCircle className="h-4 w-4" /> 연결 실패</span>}
          </div>
        </div>
      </AdminSection>

      <AdminSection title="파이프라인">
        <div className="max-w-sm">
          <div className="flex items-center justify-between rounded-lg border border-gray-200 p-3">
            <div>
              <p className="text-sm font-medium text-gray-800">8-Phase 파이프라인</p>
              <p className="text-xs text-gray-400">청킹+SceneDirector 경로 사용. OFF 시 레거시 generate_script 사용.</p>
            </div>
            <Controller
              name="use_content_processor"
              control={control}
              render={({ field }) => (
                <Switch
                  id="use_content_processor"
                  checked={field.value}
                  onChange={(e) => field.onChange(e.target.checked)}
                />
              )}
            />
          </div>
        </div>
      </AdminSection>

      <AdminSection title="TTS">
        <div className="max-w-sm space-y-4">
          <div>
            <Label className="mb-1 block">목소리</Label>
            <Select value={ttsVoice} onValueChange={(v) => setValue('tts_voice', v)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {voices.map((v) => (
                  <SelectItem key={v.key} value={v.key}>{v.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="mt-1 text-xs text-gray-400">Fish Speech 목소리 프리셋. (voices.json 기반)</p>
          </div>
        </div>
      </AdminSection>

      <AdminSection title="자동화">
        <div className="max-w-sm space-y-5">
          <div className="flex items-center justify-between rounded-lg border border-gray-200 p-3">
            <div>
              <p className="text-sm font-medium text-gray-800">자동 승인</p>
              <p className="text-xs text-gray-400">engagement score 임계값 이상 게시글을 크롤링 즉시 승인</p>
            </div>
            <Controller
              name="auto_approve_enabled"
              control={control}
              render={({ field }) => (
                <Switch
                  id="auto_approve_enabled"
                  checked={field.value}
                  onChange={(e) => field.onChange(e.target.checked)}
                />
              )}
            />
          </div>

          {autoApproveEnabled && (
            <div>
              <Label className="mb-1 block">자동 승인 임계값 (engagement score)</Label>
              <Input type="number" {...register('auto_approve_threshold')} />
              <p className="mt-1 text-xs text-gray-400">기본값 80 — 이 점수 이상인 게시글만 자동 승인됩니다.</p>
            </div>
          )}

          <div className="flex items-center justify-between rounded-lg border border-gray-200 p-3">
            <div>
              <p className="text-sm font-medium text-gray-800">자동 업로드</p>
              <p className="text-xs text-gray-400">렌더링 완료 후 YouTube에 자동 업로드</p>
            </div>
            <Controller
              name="auto_upload"
              control={control}
              render={({ field }) => (
                <Switch
                  id="auto_upload"
                  checked={field.value}
                  onChange={(e) => field.onChange(e.target.checked)}
                />
              )}
            />
          </div>

          {autoUpload && (
            <div>
              <Label className="mb-1 block">업로드 공개 범위</Label>
              <select
                {...register('upload_privacy')}
                className="w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="unlisted">일부 공개 (비공개 링크)</option>
                <option value="public">전체 공개</option>
                <option value="private">비공개</option>
              </select>
              <p className="mt-1 text-xs text-gray-400">YouTube 업로드 시 적용되는 공개 범위입니다.</p>
            </div>
          )}

          <div>
            <Label className="mb-1 block">줄당 최대 글자 수</Label>
            <Input type="number" {...register('max_chars_per_line')} />
          </div>
        </div>
      </AdminSection>
    </form>
  )
}
