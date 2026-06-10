# GPU 효율 개선 3종 결과

## 1. 작업 결과

GPU 유휴 시간을 줄이는 3가지 개선을 구현했습니다.

| 개선 항목 | 예상 효과 |
|---|---|
| Phase 5 ∥ Phase 6 병렬화 | VIDEO_GEN_ENABLED=true일 때 video_prompt LLM 시간만큼 단축 |
| Fish Speech 워밍업 센티널 | ai_worker 재시작 시 ~30-60초 워밍업 생략 (6시간 이내) |
| 하트비트 + 프론트엔드 배지 | 멈춘 PROCESSING 항목을 15분 후 UI에서 시각 감지 |

---

## 2. 수정 내용

### `worker/ai_worker/pipeline/content_processor.py`

**추가 import:** `asyncio`, `datetime`, `db.models.Post`, `db.session.SessionLocal`

**`_touch_post(post_id)` 신규 함수:**
- Phase 완료 시점마다 `updated_at`을 `datetime.utcnow()`로 터치
- DB 오류는 경고 로그만 남기고 파이프라인 중단 없음

**하트비트 삽입 지점 (총 8곳):**
1. Phase 1 완료 후
2. Phase 3 완료 후
3. Phase 4 완료 후
4. Phase 4.5 완료 후 (VIDEO_GEN_ENABLED=true 시)
5. Phase 5 & 6 완료 후
6. VRAM clear (`_clear_vram_for_video`) 완료 후
7. Phase 7 씬 1개 완료마다 (`on_scene_complete` 콜백)
8. Phase 7 전체 완료 후

**Phase 5 ∥ Phase 6 병렬화:**
- Phase 5 로직을 `_run_tts_phase(scene_list)` 내부 async 함수로 분리
- `VIDEO_GEN_ENABLED=true`일 때 `asyncio.gather(_run_tts_phase, _run_phase6)` 병렬 실행
- Phase 6 (`generate_batch`)는 sync 함수이므로 `run_in_executor(None, lambda: ...)` 래핑
- `VIDEO_GEN_ENABLED=false`이면 Phase 5만 순차 실행 (기존 동작 완전 보존)
- `body_summary` 변수는 두 분기 모두에서 정의됨

### `worker/ai_worker/tts/fish_client.py`

**추가 import:** `json`, `time`

**신규 함수 3개:**
- `_get_warmup_sentinel_path()` → `MEDIA_DIR/tmp/fish_warmup_state.json`
- `_load_warmup_sentinel()` → dict(warmed_at, url) | None
- `_save_warmup_sentinel()` → warmed_at + FISH_SPEECH_URL 기록

**`_warmup_model()` 수정:**
- 시작 시 센티널 로드 및 유효성 검사 (6시간 이내 + URL 일치)
- 센티널 유효: 1회 프로브("안녕하세요.") 전송 → 200응답이면 즉시 `_warmup_done=True`, 나머지 워밍업 전부 스킵
- 프로브 실패 또는 센티널 없음/만료: 기존 풀 워밍업(3회 기본 + 비기본 음성 프리셋) 실행
- 풀 워밍업 성공 시 `_save_warmup_sentinel()` 호출
- 프로세스 내 `_warmup_done` 플래그도 유지 (중복 방지)

### `frontend/app/(admin)/admin/progress/page.tsx`

**PROCESSING 카드 수정:**
- 카드 오른쪽 영역을 `<div className="flex items-center gap-2">` 로 변경
- `post.updatedAt`이 현재 시각보다 15분 이상 이전이면 `⚠ 응답 없음` 배지 추가
- `&#9888;` (경고 기호) + `text-xs text-yellow-500` 스타일로 기존 스타일 패턴 준수

---

## 3. 테스트 결과물 저장 위치

- Fish Speech 워밍업 센티널: `assets/media/tmp/fish_warmup_state.json`
- Phase 하트비트: `posts.updated_at` 컬럼 (MariaDB)
- 프론트엔드 배지: 진행현황 페이지 `/admin/progress`

---

## 4. 수동 테스트 방법

### 변경 1: Phase 5 ∥ Phase 6 병렬화

```bash
# VIDEO_GEN_ENABLED=true 상태에서 ai_worker 실행
docker compose -f env/docker-compose.yml logs --tail 100 ai_worker | grep -E "Phase 5|Phase 6|병렬"
# 예상 출력:
# [content_processor] Phase 5 & 6 병렬 시작 (TTS ∥ video_prompt)
# [content_processor] Phase 5 완료: TTS 성공=N 실패=0
# [content_processor] Phase 6 완료: N개 프롬프트 생성
```

### 변경 2: Fish Speech 워밍업 센티널

```bash
# ai_worker 첫 기동 후 센티널 생성 확인
cat assets/media/tmp/fish_warmup_state.json
# {"warmed_at": 1749..., "url": "http://fish-speech:8080"}

# ai_worker 재시작 후 로그 확인
docker compose -f env/docker-compose.yml restart ai_worker
docker compose -f env/docker-compose.yml logs --tail 30 ai_worker | grep warmup
# 예상: "Fish Speech 워밍업 스킵 (캐시 유효, X.Xh 전 웜업)"
```

### 변경 3: 하트비트 + 프론트엔드 배지

```bash
# PROCESSING 게시글의 updated_at이 Phase마다 갱신되는지 확인
docker compose -f env/docker-compose.yml exec db mysql -uwagglebot -pwagglebot wagglebot \
  -e "SELECT id, status, updated_at FROM posts WHERE status='PROCESSING';"
# Phase 완료마다 updated_at이 현재 시각에 가깝게 갱신되어야 함

# 프론트엔드: /admin/progress 에서 15분 이상 updated_at이 지난 PROCESSING 카드에
# "⚠ 응답 없음" 배지가 표시되는지 확인
```

---

## 5. 추천 commit message

```
perf: Phase5∥Phase6 병렬화 + Fish Speech 워밍업 센티널 + PROCESSING 하트비트

- asyncio.gather로 TTS(Phase 5)와 video_prompt 생성(Phase 6) 병렬 실행
  (VIDEO_GEN_ENABLED=false면 기존 순차 동작 유지)
- Fish Speech 워밍업 결과를 fish_warmup_state.json 센티널로 영속화
  (6시간 이내 재시작 시 1회 프로브 후 나머지 워밍업 스킵 ~30-60초 단축)
- Phase 1~8 완료 시점 및 Phase 7 씬별 체크포인트에서 updated_at 터치 (8곳)
- 진행현황 PROCESSING 카드에 updated_at 15분 초과 시 "⚠ 응답 없음" 배지 추가
```
