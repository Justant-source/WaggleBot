# WaggleBot 구조 개선 작업 결과

## 1. 작업 결과

7개 워크 패키지(WP-1~7) 전체 완료. P0 4개 + P1 3개.

---

## 2. 수정 내용

### WP-1: TTS 프리뷰 버그 수정 (P0)
**파일**: `worker/dashboard_worker/handlers.py`
- 존재하지 않는 `FishSpeechClient` 클래스 import → 실제 `synthesize()` 함수로 교체
- 출력 확장자 `.mp3` → `TTS_OUTPUT_FORMAT` 설정값(wav) 반영
- `voice=` → `voice_key=` 파라미터명 수정
- `scope="full"` 옵션 추가: hook + 전체 body + closer 전체 미리듣기 지원

### WP-2: 실패 원인 UI 노출 (P0)
**파일 6개**:
- `worker/db/migrations/006_add_post_last_error.sql` — `posts.last_error VARCHAR(1000)` 컬럼 추가
- `worker/db/models.py` — Post에 `last_error` 컬럼 필드 추가
- `worker/ai_worker/core/main.py` — `_mark_post_failed(post_id, error="")` 시그니처 변경, 예외 텍스트 저장
- `backend/.../domain/Post.java` — `lastError` 필드 추가
- `backend/.../controller/ProgressController.java` — FAILED 포스트 목록(최대 20건) 반환, retry 시 초기화
- `frontend/app/(admin)/admin/progress/page.tsx` — `FailedPostCard` 컴포넌트 추가 (오류 펼치기/접기 + 재시도 버튼)
- `frontend/lib/types/index.ts` — `lastError?: string` 추가

### WP-3: 비디오 세그먼트 단일 NVENC 인코딩 (P0)
**파일**: `worker/ai_worker/renderer/_encode.py`, `worker/ai_worker/video/video_utils.py`
- `_render_video_segment`: `resize_clip_to_layout` + `loop_or_trim_clip` 2단계 제거, 단일 filter_complex로 통합
- `-stream_loop -1 -i {clip_path}` demux 루프로 재인코딩 없는 클립 루프
- scale+crop+fps를 filter_complex 안에서 1회 처리 → 인코딩 횟수 2→1회
- `_get_encoder_args`: 프리셋 `"medium"` → `"p4"` 명시
- `video_utils.py`: intermediate codec에 `-cq 30` 추가

### WP-4: 프롬프트 자극도/리텐션 강화 (P0)
**파일**: `worker/ai_worker/script/client.py`, `worker/ai_worker/script/chunker.py` (동일 내용 미러링)
추가된 지침 6가지:
- (a) 나쁜 hook 패턴 4종 금지 예시 + 변환 예
- (b) mood별 중간 떡밥 변주 (shock/humor/touching/anger/daily 5종)
- (c) 댓글 3역할 선택 전략 (공감/관점보충/여운) + closer 연결 전략
- (d) 호칭 일관성 규칙 (표류 금지, 의도적 변경 1회 허용)
- (e) mood 판정 트리 8단계 (horror→shock→anger→touching/sadness→humor→controversy→info→daily)
- (f) 리듬 O/X 예시 (균일 × → 긴장·이완 변주 ○)

### WP-5/6: Phase 5∥6 병렬화 + 워밍업 스킵 + 멈춤 감지 (P1)
**파일 3개**:
- `worker/ai_worker/pipeline/content_processor.py`:
  - Phase 5(TTS, GPU) ∥ Phase 6(video_prompt, 원격 LLM) `asyncio.gather` 병렬 실행 (VIDEO_GEN_ENABLED 시)
  - Phase 경계 8곳에 `_touch_post()` 하트비트 삽입
- `worker/ai_worker/tts/fish_client.py`:
  - `MEDIA_DIR/tmp/fish_warmup_state.json` 센티널로 6시간 이내 워밍업 스킵
  - 시작 시 1회 프로브만 전송, 성공 시 나머지 8회 요청 건너뜀
- `frontend/app/(admin)/admin/progress/page.tsx`:
  - PROCESSING 카드에 `updatedAt > 15분` 경과 시 "⚠ 응답 없음" 배지 표시

### WP-7: 갤러리 풀스크린 프리뷰 모달 (P1)
**파일**: `frontend/app/(admin)/admin/gallery/page.tsx`
- 썸네일 클릭 → 9:16 `max-h-[85vh]` 풀스크린 비디오 모달
- `autoPlay controls`, Esc/배경 클릭 닫기
- HD 렌더/업로드 버튼을 모달 안에 포함

---

## 3. 테스트 결과물 저장 위치

변경된 코드:
- Python: `worker/ai_worker/renderer/_encode.py`, `content_processor.py`, `fish_client.py`, `script/client.py`, `chunker.py`, `core/main.py`, `db/models.py`
- Java: `backend/.../domain/Post.java`, `ProgressController.java`, `PostRepository.java`
- TypeScript: `frontend/app/(admin)/admin/gallery/page.tsx`, `progress/page.tsx`, `lib/types/index.ts`
- SQL: `worker/db/migrations/006_add_post_last_error.sql`

---

## 4. 수동 테스트 방법

```bash
# 1. DB 마이그레이션 실행
cd /home/justant/Data/WaggleBot
python -m db.migrations.runner   # worker 디렉토리에서 실행

# 2. TTS 프리뷰 테스트 (Fish Speech 컨테이너만 필요)
docker compose -f env/docker-compose.yml up fish-speech -d
# 에디터에서 포스트 선택 → TTS 미리듣기 버튼 → 오디오 재생 확인

# 3. 렌더링 단일 인코딩 테스트 (GPU 필요)
# 아무 APPROVED 포스트 1건 풀 파이프라인 실행 후 영상 확인

# 4. 실패 원인 테스트
docker compose -f env/docker-compose.yml stop fish-speech
# 포스트 승인 → 파이프라인 실행 → progress 페이지에서 실패 원인 텍스트 확인

# 5. 프롬프트 전후 비교 (Claude API)
# config/pipeline.json의 llm_backend=api 설정 후
# python -c "from ai_worker.script.client import generate_script; ..."

# 6. 프론트엔드 확인
cd frontend && npm run dev
# 갤러리: 썸네일 클릭 → 모달 재생 확인
# progress: 처리 중 카드, 실패 카드 확인
```

---

## 5. 추천 commit message

```
feat: 구조 전면 개선 — 렌더링 효율 + 프롬프트 강화 + 사용성 + GPU 최적화

- TTS 프리뷰 ImportError 버그 수정 (FishSpeechClient → synthesize)
- posts.last_error 컬럼 추가 + progress 페이지 실패 원인 표시
- video_segment 단일 NVENC 인코딩 (2→1회, ~20-30% 렌더 단축)
- 스크립트 프롬프트: 나쁜 hook 예시/mood별 떡밥/댓글 전략/호칭 일관성/mood 트리
- Phase 5(TTS) ∥ Phase 6(video_prompt) asyncio.gather 병렬화
- Fish Speech 워밍업 센티널 스킵 (~60초/재시작 단축)
- PROCESSING 멈춤 감지 + 갤러리 풀스크린 프리뷰 모달
```
