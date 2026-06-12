# 설정 페이지 음성 목록 동적 로드

## 1. 작업 결과

`settings/page.tsx` TTS 음성 드롭다운이 `voices.json`과 분리되어 하드코딩되어 있던 문제 수정.
`ttsApi.voices()`로 동적 로드 → `voices.json` 변경이 UI에 즉시 반영됨.

## 2. 수정 내용

**`frontend/app/(admin)/admin/settings/page.tsx`**

```diff
+ import { ttsApi } from '@/lib/api/tts'
+ import type { VoiceInfo } from '@/lib/types'

+ const [voices, setVoices] = useState<VoiceInfo[]>([])

  // useEffect
+ ttsApi.voices().then((res) => setVoices(res.voices)).catch(() => {})

  // SelectContent
- <SelectItem value="default">기본 남성 내레이터</SelectItem>
- <SelectItem value="anna">Anna (여, 친근한 내레이션)</SelectItem>
- ... (8개 하드코딩)
+ {voices.map((v) => (
+   <SelectItem key={v.key} value={v.key}>{v.label}</SelectItem>
+ ))}
```

- API 실패 시(백엔드 미기동 등) `voices` 빈 배열 유지 — 드롭다운 비어있으나 crashe 없음
- 기존 `ttsApi` 및 `VoiceInfo` 타입은 이미 정의되어 있었음 (`lib/api/tts.ts`, `lib/types/index.ts`)

## 3. 테스트 결과물 위치

개발서버 `npm run dev` 후 `/admin/settings` → TTS 목소리 섹션 확인

## 4. 수동 테스트 방법

```bash
# 백엔드 + 프론트엔드 실행 후
# /admin/settings 접속 → TTS 섹션 음성 드롭다운이 voices.json 기반으로 표시되는지 확인
# voices.json에 새 음성 추가 후 백엔드 재시작 → 드롭다운에 반영 확인
```

## 5. 추천 commit message

```
fix: 설정 페이지 TTS 음성 목록 하드코딩 → ttsApi.voices() 동적 로드
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 (frontend UI 변경, docs에 영향 없음)
