# WaggleBot E2E 파이프라인 테스트 결과

> **실행일:** 2026-06-14  
> **테스트 실행:** 2회 (Pass A: post_id=10000629, Pass B: post_id=10000247)

---

## 1. 전체 PASS/FAIL 요약 (게이트별 표)

### Pass A — post_id=10000629 (VIDEO_GEN_ENABLED=false)

| 게이트 | 내용 | 결과 | 비고 |
|--------|------|------|------|
| G0 | 사전조건 체크 | PASS (부분) | YouTube OAuth 없음 (예상), voice 참조파일 다수 누락 |
| G1 | 크롤링 | PASS | MANUAL_CRAWL job_id=56, 신규 6건 |
| G2 | 수신함 승인 → EDITING | PASS | GENERATE_SCRIPT job_id=57 생성 |
| G3 | 대본 생성 (ScriptData) | PASS | hook/body 19개/closer/comment_scenes=3/mood=shock |
| G4 | 대본 확정 → APPROVED | PASS | |
| G5 | 8-Phase → PREVIEW_RENDERED | PASS | 4.5분, TTS+layout+FFmpeg (VIDEO_GEN_ENABLED=false) |
| G6 | HD 렌더 → RENDERED | FAIL→(BUG-01 확인) | dashboard_worker GPU 미설정, 사용자 허가로 수정 |
| G7 | YouTube 업로드 | BLOCKED+BUG | OAuth 없음이지만 silent skip+UPLOADED 전환 (BUG-03/04) |

### Pass B — post_id=10000247 (VIDEO_GEN_ENABLED=true)

| 게이트 | 내용 | 결과 | 비고 |
|--------|------|------|------|
| G2 | 수신함 승인 → EDITING | PASS | GENERATE_SCRIPT job_id=60 |
| G3 | 대본 생성 | PASS | hook/body 16개/closer/comment_scenes=3/mood=humor |
| G4 | 대본 확정 → APPROVED | PASS | |
| G5 | 8-Phase → PREVIEW_RENDERED | PASS | 30분, Phase 4.5~7(LTX-2) + Phase 8(FFmpeg) |
| G6 | HD 렌더 → RENDERED | **PASS** | GPU 설정 추가 후 성공 |
| G7 | YouTube 업로드 | BLOCKED | YouTube OAuth 미설정 — /goal 탈출 조건 적용 |

**종합 Pass B: G2~G6 모두 PASS, G7 BLOCKED(OAuth 미설정) → RENDERED 완주**

---

## 2. post_id 및 최종 상태 추적

### Pass A — post_id=10000629 (dcinside)
```
title: 앤트로픽 페이블로 만든 월드오브워크래프트 스타일 MMORPG (추가)
engagement_score: 70326.8 / comment_count: 57

COLLECTED → EDITING (G2, 14:00) → APPROVED (G4) 
→ PROCESSING (05:00:45 UTC) → PREVIEW_RENDERED (05:05:23 UTC, 4.5분)
→ UPLOADED (G7 silent skip — 실제 업로드 없음)
최종 DB: posts.status=UPLOADED, contents.upload_meta={thumbnail_path} (video_id 없음)
```

### Pass B — post_id=10000247 (theqoo)
```
title: 일본에서 엄청 터진 울산시 공무원 줌회의ㅋㅋㅋㅋㅋㅋㅋㅋ
engagement_score: 6483.2 / comment_count: 64

COLLECTED → EDITING (G2, 14:25) → APPROVED (G4, 14:26)
→ PROCESSING (05:26:25 UTC) → PREVIEW_RENDERED (05:56:08 UTC, 30분)
→ RENDERED (G6, job_id=61, 14:57)
최종 DB: posts.status=RENDERED
```

---

## 3. 산출 파일 경로 및 ffprobe 결과

### Pass A (post_id=10000629)

| 파일 | 경로 | 크기 |
|------|------|------|
| 오디오 | `/app/media/audio/dcinside/post_dcbest_436939.wav` | 3.7MB |
| 비디오 (SD) | `/app/media/video/dcinside/post_dcbest_436939_SD.mp4` | 2.3MB |
| 썸네일 | `/app/media/thumbnails/dcinside/post_dcbest_436939.jpg` | 47KB |

**ffprobe — SD 비디오 (post_id=10000629)**
```
Stream 0: h264  1080x1920  duration=61.97s
Stream 1: aac   duration=60.20s
```
오디오: 43.8초, 3.7MB WAV

### Pass B (post_id=10000247)

| 파일 | 경로 | 크기 |
|------|------|------|
| 오디오 | `/app/media/audio/theqoo/post_4241357550.wav` | — |
| 비디오 (SD) | `/app/media/video/theqoo/post_4241357550_SD.mp4` | — |
| 비디오 (FHD) | `/app/media/videos/10000247_FHD.mp4` | 1.1MB |
| 썸네일 | `/app/media/thumbnails/theqoo/post_4241357550.jpg` | — |

**ffprobe — FHD 비디오 (post_id=10000247, G6 산출물)**
```
Stream 0: h264  1080x1920  duration=32.13s
Stream 1: aac   duration=30.69s
```

**ADR-0002 검증:** `_encode.py` `_resolve_codec()` → `h264_nvenc` (폴백 없음) ✓

**LTX-2 클립 생성 현황 (Pass B Phase 7):**
- 씬 0,1,4,6,7,8,13 포함 7+ 클립 성공 (ltx2_t2v_distilled_00048~00053.mp4)
- Distilled 모드 (steps=8, cfg=1.0, 1280×720, 129프레임)
- 클립당 평균 ~2.5~4분

---

## 4. 발견한 결함·이상치 목록 (수정 없이 기록 → BUG-01은 사용자 허가로 수정)

### 버그

**BUG-01 [치명, 사용자 허가로 수정 완료] dashboard_worker GPU 미설정 → HD_RENDER h264_nvenc 초기화 실패**
- 위치: `env/docker-compose.yml` — `dashboard_worker` 서비스에 NVIDIA 런타임 미설정
- 현상: HD_RENDER job 실행 시 FFmpeg에서 `Error while opening encoder for output stream #0:0`
- Pass A에서 FAIL 확인, 사용자 허가 후 GPU 설정 추가 → Pass B에서 PASS
- 수정 내용: `/usr/lib/wsl/lib` 볼륨 마운트, NVIDIA_VISIBLE_DEVICES/LD_LIBRARY_PATH 환경변수, deploy.resources.devices 추가

**BUG-02 [중간] HD_RENDER job 실패 후 post 상태 FAILED 미전환 (PREVIEW_RENDERED 유지)**
- HD_RENDER job이 ERROR 상태가 되어도 posts.status = PREVIEW_RENDERED 유지
- 사용자가 갤러리에서 해당 포스트가 성공한 것처럼 보임

**BUG-03 [중간] YouTube 인증 실패 시 UPLOAD job이 silent skip 후 DONE 반환**
- `config/youtube_token.json` 없을 때 "youtube 인증 실패, 건너뜀" 경고만 출력하고 job status=DONE
- 예상 동작: 업로더 인증 실패 시 job status=ERROR

**BUG-04 [중간] 실제 업로드 없이 post 상태 UPLOADED 전환 (Pass A에서 관찰)**
- 원인: BUG-03 연계 — UPLOAD job DONE 시 post.status=UPLOADED
- 확인: `contents.upload_meta`에 video_id 없음 (thumbnail_path만 존재)

### 이상치 (버그 아님)

**INFO-01: dcinside/theqoo 이미지 403 Forbidden 핫링크 차단**
- Phase 8에서 이미지 다운로드 실패 → text_only 폴백으로 정상 처리 ✓
- HD_RENDER도 동일하게 403 발생 후 폴백 동작 확인

**INFO-02: voice 참조파일 다수 누락 (기본 음색 사용)**
- manu/miguel/min_jun/norah/tara/theo/yohan_koo/yura 등 기본 음색 사용
- TTS 동작 자체는 정상 (기본 음색으로 합성됨)

**INFO-03: `/api/gallery/jobs/{jobId}` 엔드포인트 없음 (500 반환)**
- Gallery job 폴링 엔드포인트가 없음 (API 문서 미반영)
- jobs 테이블 직접 SELECT로 상태 확인 필요

**INFO-04: HD_RENDER가 기존 TTS 캐시를 무시하고 전체 재렌더링**
- SD 렌더링 후 캐시된 TTS 파일이 있으나 HD_RENDER는 새 TTS를 생성
- 불필요한 재처리 (~3분 추가 소요)

**INFO-05: Phase 7 중 _touch_post 미갱신 (15분 경과)**
- Phase 7 내 클립별 폴링 중에는 posts.updated_at 미갱신 (Phase 경계에서만 갱신)
- 30분 이상 소요 시 프론트엔드 "응답 없음" 배지가 표시될 수 있음

**INFO-06: VIDEO_WORKFLOW_MODE=full 설정 무시 (Distilled 모드 사용)**
- `.env`에 `VIDEO_WORKFLOW_MODE=full` 설정되어 있으나
  실제로는 `Distilled 모드 (steps=8, cfg=1.0)`으로 실행됨
- 모델 파일 자체가 `ltx-2-19b-distilled_Q4_K_M.gguf` (distilled GGUF)이므로
  full 모드 전환이 동작하지 않는 것으로 추정

---

## 5. 수동 재현 방법

### 전제조건
```bash
# 서비스 기동 (GPU 포함)
docker compose -f env/docker-compose.yml ps

# VIDEO_GEN_ENABLED=false (Pass A - 빠른 체인 검증)
# env/.env: VIDEO_GEN_ENABLED=false
docker compose -f env/docker-compose.yml up -d --no-deps --force-recreate ai_worker

# VIDEO_GEN_ENABLED=true (Pass B - LTX-2 포함)
# env/.env: VIDEO_GEN_ENABLED=true
docker compose -f env/docker-compose.yml up -d --no-deps --force-recreate ai_worker
```

### 단계별 실행
```bash
POST_ID=10000247  # COLLECTED이고 댓글 있는 포스트 선택

# G1: 크롤링 (또는 기존 COLLECTED 재사용)
curl -X POST http://localhost:8080/api/inbox/crawl

# G2: 승인
curl -X POST http://localhost:8080/api/inbox/${POST_ID}/approve

# G3: GENERATE_SCRIPT 완료 대기 (수십 초)
# curl http://localhost:8080/api/editor/jobs/{jobId} → DONE 확인

# G4: 확정
curl -X POST http://localhost:8080/api/editor/${POST_ID}/confirm

# G5: PREVIEW_RENDERED 대기
# VIDEO_GEN_ENABLED=false: 4-5분
# VIDEO_GEN_ENABLED=true: 20-40분 (LTX-2 클립 수에 따라)
docker compose -f env/docker-compose.yml exec db mariadb -u wagglebot -pwagglebot wagglebot -e \
  "SELECT status, updated_at FROM posts WHERE id=${POST_ID};"

# G6: HD 렌더
curl -X POST http://localhost:8080/api/gallery/${POST_ID}/hd-render
# jobs 테이블 폴링: SELECT status,error FROM jobs WHERE post_id=${POST_ID} ORDER BY id DESC LIMIT 1;
# 완료: posts.status = RENDERED

# G7: (YouTube OAuth 필요)
# config/youtube_token.json 설정 후:
curl -X POST http://localhost:8080/api/gallery/${POST_ID}/upload \
  -H "Content-Type: application/json" -d '{"platform":"youtube"}'
```

### YouTube OAuth 설정 (G7 활성화)
```bash
# 업로더가 읽는 토큰 파일: config/youtube_token.json
# OAuth 플로우: worker/uploaders/youtube.py의 인증 플로우 참고
# upload_privacy 확인 필수:
python3 -c "import json; d=json.load(open('config/pipeline.json')); print(d.get('upload_privacy'))"
# → 'unlisted' 또는 'private'이어야 함 (현재: unlisted)
```

---

## 6. DOC-MAP 기준 갱신이 필요한 문서

| 문서 | 갱신 이유 |
|------|-----------|
| `docs/services.md` | dashboard_worker에 GPU 설정 추가됨 명시 (BUG-01 수정 반영) |
| `docs/api.md` | `/api/gallery/jobs/{jobId}` 미존재 명시 또는 엔드포인트 추가 필요 |
| `docs/pipeline.md` | Phase 7 _touch_post 미갱신 관련 설명 추가 (30분+ 소요 시 "응답 없음" 배지) |
| `docs/implementation-status.md` | BUG-02/03/04 버그 기록, INFO-06 VIDEO_WORKFLOW_MODE=full 미동작 기록 |

---

## 7. 결론

- **Pass A (VIDEO_GEN_ENABLED=false):** G1~G5 PASS (4.5분), G6 FAIL (BUG-01), G7 BLOCKED+BUG
- **BUG-01 수정 (사용자 허가):** docker-compose.yml dashboard_worker GPU 설정 추가
- **Pass B (VIDEO_GEN_ENABLED=true):** G2~G6 PASS (30분, LTX-2 클립 포함), G7 BLOCKED(OAuth)
- **최종 달성 상태:** RENDERED (post_id=10000247, 2026-06-14 14:57 KST)
- **YouTube 업로드 (G7):** config/youtube_token.json 없음 → /goal 탈출 조건 적용 (RENDERED까지 완주)
