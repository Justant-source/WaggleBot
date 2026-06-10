# WaggleBot 구조 개선 — 설계 컨텍스트

> 이 문서는 2026-06-10 전수 조사 후 단행한 7개 워크 패키지(WP-1~7)와 P2 보완 작업의
> 설계 결정 이유와 변경 내용을 기록한다.

---

## 배경

코드베이스 전수 조사 결과 발견한 4가지 구조적 문제:

| 문제 | 영향 |
|------|------|
| `FishSpeechClient` ImportError | TTS 프리뷰 잡이 모두 묵살 실패 |
| NVENC 2회 인코딩 | 씬당 렌더 ~20-30% 낭비 + 품질 손실 중간파일 |
| `last_error` 컬럼 없음 | 실패 원인이 로그에만 존재, UI 블랙박스 |
| Phase 5(TTS)↔Phase 6(video_prompt) 순차 실행 | haiku 30-90초가 TTS에 직렬 추가 |

---

## WP-1: TTS 프리뷰 버그 수정

**파일**: `worker/dashboard_worker/handlers.py`

`FishSpeechClient`라는 클래스는 존재한 적 없다. `fish_client.py`는 모듈-레벨 `async def synthesize()` 함수만 노출한다.

```python
# 수정 전 (ImportError)
from ai_worker.tts.fish_client import FishSpeechClient
client = FishSpeechClient()
audio = client.synthesize(text)

# 수정 후
import asyncio
from ai_worker.tts.fish_client import synthesize
audio_path = asyncio.run(synthesize(text, voice_key=voice_key, output_path=output_path))
```

`scope="full"` 옵션도 추가해 hook + body 전체 + closer를 한 번에 들을 수 있다.
dashboard_worker는 단일 스레드 sync 프로세스이므로 `asyncio.run` 사용이 안전하다.

---

## WP-2: 실패 원인 end-to-end 노출

**신규 마이그레이션**: `worker/db/migrations/006_add_post_last_error.sql`

```sql
ALTER TABLE posts ADD COLUMN IF NOT EXISTS last_error VARCHAR(1000) NULL;
```

이전까지 예외는 로그에만 남았다. `_mark_post_failed(post_id, error: str = "")` 시그니처를 변경해 `repr(exc)[:1000]`을 DB에 기록하게 했다. PROCESSING 재진입 시 `last_error = None`으로 초기화한다.

프론트엔드 `FailedPostCard` 컴포넌트:
- 오류 텍스트 펼치기/접기 (`<pre>` 스크롤)
- 재시도 버튼 → `progressApi.retry(id)` → backend `APPROVED`로 복원

---

## WP-3: 비디오 세그먼트 단일 NVENC 인코딩

**파일**: `worker/ai_worker/renderer/_encode.py`

이전 흐름:
1. `resize_clip_to_layout` — p1 프리셋, CQ 미지정 → **1차 인코딩** (비트레이트 기아 발생 가능)
2. `loop_or_trim_clip` — 길이 맞춤 **2차 인코딩**
3. filter_complex 오버레이 합성 → **3차 인코딩**

현재 흐름: 단일 FFmpeg 명령으로 통합

```
ffmpeg -y
  -i base.png                         # 정적 배경
  -stream_loop -1 -i clip.mp4         # demux 루프 (재인코딩 없음)
  -i txtoverlay.png
  -filter_complex
    "[0:v]loop=loop=N:size=1...[base];
     [1:v]scale=W:H:...,crop=W:H,fps=30[clip];
     [base][clip]overlay=X:Y:shortest=0[vwith];
     [2:v]scale=CW:CH[txt];
     [vwith][txt]overlay=0:0[vout]"
  -map [vout] -t {duration}
  -c:v h264_nvenc -preset p4 -cq 23 -r 30 -an
```

`-stream_loop -1`은 demux 레벨 루프이므로 원본 LTX 클립의 비트스트림이 그대로 흐른다. scale/crop/fps는 filter_complex에서 1회만 처리된다.

`"medium"` → `"p4"` 명시: NVENC 신규 API에서 p4는 medium 동등 품질이다. concat 단계는 이미 `-c copy`이므로 영향 없다.

---

## WP-4: 프롬프트 자극도/리텐션 강화

**파일**: `worker/ai_worker/script/client.py` (`_SCRIPT_SYSTEM`), `worker/ai_worker/script/chunker.py` (`build_chunking_system`)

두 파일은 같은 시스템 프롬프트를 각각 유지한다. 캐시 prefix 교체로 1회 캐시 미스가 발생하지만 이후 정상 캐시된다.

추가된 지침 6가지:

| 지침 | 목적 |
|------|------|
| (a) 나쁜 hook 예시 4종 + 변환 예 | 명사형 요약 hook 방지 |
| (b) mood별 중간 떡밥 5변주 | 매번 같은 문구 방지 |
| (c) 댓글 3역할 선택 전략 | 공감/관점보충/여운 균형 |
| (d) 호칭 일관성 규칙 | 인물 표류 방지 |
| (e) mood 판정 트리 8단계 | horror→shock→anger→touching/sadness→humor→controversy→info→daily |
| (f) 리듬 O/X 예시 | 기계적 균일 줄 방지 |

mood 판정 트리는 가장 영향이 크다. 이전 프롬프트에는 판정 기준이 없어 `daily`나 `info`로 과도하게 수렴했다.

---

## WP-5: Phase 5∥6 병렬화

**파일**: `worker/ai_worker/pipeline/content_processor.py`

Phase 5(TTS): `scene.text_lines[j] = {"text": ..., "audio": ...}` 변경
Phase 6(video_prompt): `scene.video_prompt` 변경

두 Phase가 접근하는 필드가 완전히 분리되어 있어 `asyncio.gather`가 안전하다.

```python
(tts_ok, tts_fail), scenes = await asyncio.gather(
    _run_tts_phase(scenes),
    _run_phase6(),          # run_in_executor로 sync 래핑
)
```

Phase 6은 원격 haiku만 사용하므로 GPU 충돌이 없다. 씬 20개 기준 haiku 누적 대기 시간(30-90초)이 TTS 시간 안에 숨는다.

`VIDEO_GEN_ENABLED=false`일 때는 기존 순차 실행을 유지한다.

---

## WP-6a: Fish Speech 워밍업 센티널 스킵

**파일**: `worker/ai_worker/tts/fish_client.py`

ai_worker 컨테이너가 재시작될 때마다 9회의 워밍업 요청이 실행됐다(~30-60초).
이제 `MEDIA_DIR/tmp/fish_warmup_state.json`에 마지막 워밍업 시각을 기록한다.

```json
{"warmed_at": 1749123456.789, "fish_url": "http://fish-speech:8080"}
```

재시작 시: 센티널이 6시간 이내이고 1회 저비용 프로브("안녕하세요.")가 성공이면 나머지 8회 스킵.
컨테이너 URL이 바뀌었거나 프로브가 실패하면 풀 워밍업 후 센티널 재작성한다.

---

## WP-6b: 하트비트 (PROCESSING 멈춤 감지)

**파일**: `worker/ai_worker/pipeline/content_processor.py`

각 Phase 경계에 `_touch_post(post_id)`를 삽입해 `posts.updated_at`을 현재 UTC로 갱신한다.
Phase 7에서는 씬별 완료마다도 터치한다.

프론트엔드 `progress/page.tsx`: PROCESSING 카드에서 `now - updatedAt > 15분`이면 "⚠ 응답 없음" 배지를 노출한다.

---

## WP-7: 갤러리 풀스크린 프리뷰 모달

**파일**: `frontend/app/(admin)/admin/gallery/page.tsx`

썸네일 클릭 → `fixed inset-0 z-50` 오버레이. 9:16 `<video autoPlay controls>` `max-h-[85vh]`.
Esc 키 및 배경 클릭으로 닫힌다. HD 렌더/업로드 버튼이 모달 안에 포함된다.

---

## P2 보완 작업

### API 헤더 분기 (transport.py)

Anthropic 공식 엔드포인트(`api.anthropic.com`)와 프록시를 구분해 헤더를 다르게 빌드한다.
공식: `x-api-key` 헤더만. 프록시: `authorization: Bearer` 추가.

```python
def _build_api_headers(api_key: str, base_url: str) -> dict[str, str]:
    is_official = _ANTHROPIC_OFFICIAL_DOMAIN in base_url
    ...
```

### ComfyUI 폴링 최적화 (comfy_client.py)

```python
def _adaptive_interval(elapsed_secs: float) -> float:
    if elapsed_secs < 30:   return 1.0
    if elapsed_secs < 120:  return 3.0
    return 5.0
```

초반 1초 → 중반 3초 → 장기 5초로 간격을 늘린다. 기존 고정 2초 대비 장시간 생성 시 불필요한 HTTP 요청이 줄어든다.

워크플로우 JSON도 모듈-레벨 `_workflow_cache`에 캐시해 파일 재파싱을 방지한다.

### 렌더러 임시파일 즉시 정리

`layout.py`: concat 완료 직후 `seg_*.mp4` 즉시 unlink.
`_frames.py`: MD5 기반 `_overlay_cache`로 동일 텍스트+레이아웃의 오버레이 PNG 재생성 방지.

### 인박스 배치 실패 피드백 (InboxController, inbox/page.tsx)

배치 승인 응답에 `{processed, failed: [{id, error}]}`를 포함시켜 프론트엔드가 부분 실패를 toast로 노출한다.

---

## E2E 테스트

**파일**: `worker/test/test_e2e_structure_improve.py`, `worker/pytest.ini`

21개 단위 테스트(`-m unit`) + 5개 통합 테스트(FFmpeg/DB/Fish 환경 필요, 기본 스킵):

```
pytest worker/test/test_e2e_structure_improve.py -m unit
# 21 passed in 1.44s
```

| 테스트 클래스 | 검증 대상 |
|-------------|-----------|
| `TestBuildApiHeaders` | 공식/프록시 헤더 분기 |
| `TestAdaptivePolling` | 폴링 인터벌 3단계 |
| `TestScriptSystemPrompt` | 프롬프트 6개 지침 존재 확인 |
| `TestOverlayCache` | MD5 캐시 히트/미스 |
| `TestPhase56Parallel` | `asyncio.gather` 존재 확인 |
| `TestMarkPostFailedSignature` | `error` 파라미터 + sync 시그니처 |
| `TestWarmupSentinel` | 센티널 로드/저장/만료 |
| `TestRenderSegmentStructure` | filter_complex 단일 구조 확인 |
| `TestDBLastError` | `Post.last_error` 컬럼 존재 |
| `TestTTSPreviewHandler` | `synthesize` import 확인 |

---

## 변경 파일 목록

| 레이어 | 파일 |
|--------|------|
| Python (worker) | `ai_worker/core/main.py`, `core/processor.py`, `llm/transport.py`, `pipeline/content_processor.py`, `renderer/_encode.py`, `renderer/_frames.py`, `renderer/layout.py`, `script/client.py`, `script/chunker.py`, `tts/fish_client.py`, `video/comfy_client.py`, `video/video_utils.py`, `dashboard_worker/handlers.py`, `db/models.py` |
| SQL (마이그레이션) | `worker/db/migrations/006_add_post_last_error.sql` |
| Java (backend) | `domain/Post.java`, `domain/PostRepository.java`, `controller/ProgressController.java`, `controller/InboxController.java` |
| TypeScript (frontend) | `app/(admin)/admin/gallery/page.tsx`, `app/(admin)/admin/inbox/page.tsx`, `app/(admin)/admin/progress/page.tsx`, `lib/api/inbox.ts`, `lib/api/progress.ts`, `lib/types/index.ts` |
| 테스트 | `worker/test/test_e2e_structure_improve.py`, `worker/pytest.ini` |
| 설정 | `config/settings.py`, `config/pipeline.json` |
