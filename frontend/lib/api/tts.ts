import { get } from './client'
import type { VoiceInfo } from '@/lib/types'

export const ttsApi = {
  voices: () =>
    get<{ defaultVoice: string; voices: VoiceInfo[] }>('/api/tts/voices'),
}
