# progressive-test 단위 테스트 작성 결과

## 1. 작업 결과

`worker/test/test_progressive_comments.py` 신규 작성 완료.
댓글/채팅 씬의 점진적 낭독(Progressive Narration) 기능에 대한 단위 테스트 9개를 작성했다.

## 2. 수정 내용

### 신규 파일

**`worker/test/test_progressive_comments.py`**

| 테스트 함수 | 검증 내용 |
|---|---|
| `test_comments_plan_entries` | 댓글 3개 씬 → plan 엔트리 3개, item_idx 0/1/2, sent_idx 순차 증가 |
| `test_chat_plan_entries` | 채팅 4개 씬 → plan 엔트리 4개, item_idx 0/1/2/3 |
| `test_voice_override_in_sentences` | 각 sentence의 voice_override가 item["voice"]와 일치 |
| `test_get_scene_for_entry_shared_scene_idx` | 여러 엔트리가 같은 scene_idx 공유해도 올바른 SceneDecision 반환 |
| `test_empty_content_skipped` | 빈 content/text 항목은 plan 엔트리에서 제외 |
| `test_render_comments_reveal_count` | reveal_count=1,2,3 각각 PNG 생성·파일 존재 확인 |
| `test_render_comments_reveal_count_none` | reveal_count=None (레거시) PNG 생성 확인 |
| `test_render_chat_reveal_count` | reveal_count=1,2,4 각각 PNG 생성·파일 존재 확인 |
| `test_render_chat_reveal_count_none` | reveal_count=None (레거시) PNG 생성 확인 |
| `test_mixed_scenes_plan_consistency` | intro+comments+chat 혼합 시 plan 총 8개, scene 매핑 정확성 |

### 설계 결정 사항

- **빈 항목 검증:** `_scenes_to_plan_and_sentences`가 빈 content/text를 `.strip()` 후 falsy 체크로 제외함을 확인. item_idx(k)는 건너뛰되, 빈 항목 이후 엔트리의 item_idx는 원본 리스트 기준 절대 인덱스로 유지됨.
- **렌더 테스트 분리:** PIL만 사용 (TTS/FFmpeg/Fish Speech 미호출). 렌더 실패 시 PIL 오류로 즉시 감지.
- **`content_top=400`:** 실제 레이아웃 계산 없이 중간값 사용 (헤더 150px + 제목블록 약 250px 기준).

## 3. 테스트 결과물 위치

**컨테이너 내 실행 시** 렌더 테스트가 생성하는 PNG:
- `/tmp/test_progressive_comments_reveal1.png`
- `/tmp/test_progressive_comments_reveal2.png`
- `/tmp/test_progressive_comments_reveal3.png`
- `/tmp/test_progressive_comments_legacy.png`
- `/tmp/test_progressive_chat_reveal1.png`
- `/tmp/test_progressive_chat_reveal2.png`
- `/tmp/test_progressive_chat_reveal4.png`
- `/tmp/test_progressive_chat_legacy.png`

## 4. 수동 테스트 방법

```bash
# pytest 전체 실행 (컨테이너 안에서만 통과)
docker exec env-ai_worker-1 python -m pytest test/test_progressive_comments.py -v

# plan/sentences 로직 테스트만 (컨테이너 밖에서도 import 경로 문제로 실패)
docker exec env-ai_worker-1 python -m pytest test/test_progressive_comments.py::test_comments_plan_entries test/test_progressive_comments.py::test_chat_plan_entries test/test_progressive_comments.py::test_voice_override_in_sentences -v

# 렌더 결과 PNG 확인
docker exec env-ai_worker-1 ls -lh /tmp/test_progressive_*.png
```

## 5. 추천 commit message

```
test: 댓글/채팅 씬 점진적 낭독(Progressive Narration) 단위 테스트 추가

_scenes_to_plan_and_sentences의 plan 엔트리 생성(item_idx/sent_idx/
voice_override/빈 항목 제외)과 _render_comments_frame/_render_chat_frame의
reveal_count 동작을 pytest 단위 테스트 9종으로 검증.
렌더 테스트는 PIL만 사용(TTS/FFmpeg 불필요).

실행: docker exec env-ai_worker-1 python -m pytest test/test_progressive_comments.py -v
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 — 신규 테스트 파일 추가에 한정. 아키텍처·API·설정·DB 스키마 변경 없음.
