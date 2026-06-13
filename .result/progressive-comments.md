# progressive-comments — 댓글·채팅 씬 점진적 낭독 구현

## 1. 작업 결과

댓글·채팅 씬이 **단일 정지 프레임 + 무음 체류** 방식에서 **항목당 한 개씩 누적(append) 표시 + 각 항목 TTS 낭독** 방식으로 전환되었다.

- 댓글 3개 → 3프레임(1개→2개→3개 누적), 각각 TTS 낭독, 작성자별 다른 목소리
- 채팅 4개 → 4프레임(버블 1개씩 append), 각각 TTS 낭독, 발신자별 다른 목소리
- 채팅 `is_mine=true` → 내레이터 목소리
- 화면 초과 시 가장 오래된 항목부터 drop(bottom-anchor), 최신 항목(현재 낭독 중인 항목)이 항상 보임

## 2. 수정 내용

| 파일 | 변경 내용 |
|------|----------|
| `worker/ai_worker/renderer/layout.py` | `_scenes_to_plan_and_sentences()` comments/chat 분기: 단일 무음 엔트리 → 항목당 sentence+plan 엔트리(sent_idx+item_idx). Step-8 디스패치: reveal_count=(item_idx+1) 전달 |
| `worker/ai_worker/renderer/_frames.py` | `_render_comments_frame`, `_render_chat_frame`: `reveal_count` 파라미터 추가, bottom-anchor 슬라이딩 윈도우(drop-oldest) 로직 추가 |
| `worker/ai_worker/scene/director.py` | `_assign_comment_voice`, `_assign_chat_voice` 헬퍼 추가; `comment_items`에 `"voice"` 키 주입; 채팅 배치 전 발신자별 voice 사전 배정 |
| `config/scene_policy.json` | comments·chat 블록 `"narrate": true`로 변경, 주석 업데이트 |
| `worker/test/test_progressive_comments.py` | 단위 테스트 10개 (신규) |
| `worker/test/test_render_progressive_mp4.py` | E2E 렌더 검증 스크립트 (신규) |

### 핵심 설계: text_only 패턴 재사용
기존 `text_only` 씬이 이미 "줄당 plan 엔트리 + 프레임마다 누적 리스트 전달" 패턴을 구현하고 있었고, comments/chat을 이 패턴으로 전환했다. 새 렌더링 엔진 불필요.

## 3. 테스트 결과물 위치

- **단위 테스트**: `worker/test/test_progressive_comments.py` — 10/10 PASSED
- **E2E 렌더 출력**: `/app/media/tmp/progressive_test/progressive_test.mp4`
  - 13.9초, 0.47MB, h264 codec (h264_nvenc)
  - 총 9프레임: intro(1) + 댓글(3) + 채팅(4) + outro(1)
  - TTS 9청크: manbo(댓글1)/anna(댓글2)/han(댓글3), yohan×4(채팅)

## 4. 수동 테스트 방법

```bash
# 단위 테스트 (컨테이너 내)
docker compose -f env/docker-compose.yml exec -u root ai_worker bash -c \
  "python3 -m pytest /app/test/test_progressive_comments.py -v"

# E2E 렌더 테스트 (컨테이너 내)
docker compose -f env/docker-compose.yml exec ai_worker bash -c \
  "cd /app/test && python3 test_render_progressive_mp4.py"

# 출력 파일 확인
# /app/media/tmp/progressive_test/progressive_test.mp4 를 다운로드 후 재생
# → 댓글 3개 1개씩 낭독, 채팅 4개 버블 1개씩 낭독 확인
```

## 5. 추천 commit message

```
feat: 댓글·채팅 씬 점진적 낭독 — 항목별 TTS + 화자별 목소리

text_only 패턴(항목당 plan 엔트리 + 누적 프레임)을 comments/chat에 적용.
댓글은 작성자별, 채팅은 발신자별 일관된 목소리로 각 항목을 읽어줌.
화면 초과 시 bottom-anchor 슬라이딩 윈도우로 최신 항목 항상 표시.
```

## 6. DOC-MAP 기준 갱신한 문서 목록

- `docs/pipeline.md` — Phase 8(렌더러) 섹션에 comments/chat 씬 동작 방식 업데이트 권장
  - "무음 체류 → 항목별 TTS 낭독, item_idx로 reveal_count 제어" 기술
