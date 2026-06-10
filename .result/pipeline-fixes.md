# pipeline-fixes

## 1. 작업 결과

AI 파이프라인 버그 15건 수정 (Python 워커 + 프론트엔드 + 백엔드).

| 항목 | 파일 | 내용 |
|------|------|------|
| chunk_with_llm post_id+extended 누락 | `content_processor.py:77` | extended=True → mood/tags 생성 |
| SceneDirector mood 미전달 (content_processor) | `content_processor.py:99` | `mood=script.get("mood","daily")` |
| SceneDirector mood 미전달 (legacy process_with_retry) | `processor.py:144` | `mood=script.mood` |
| SceneDirector mood 미전달 (render_stage) | `processor.py:845` | `mood=script.mood` |
| repr() → str() 에러 메시지 | `processor.py:494` | 가독성 개선 |
| _MOOD_TO_STYLE 4→9종 확장 (process_with_retry) | `processor.py:166` | 9개 mood 전체 매핑 |
| _MOOD_TO_STYLE 4→9종 확장 (render_stage) | `processor.py:801` | 동일 fix, render_stage도 legacy만 있었음 |
| ScriptData 기본 mood "funny"→"daily" | `processor.py:769` | llm_tts_stage 경로 기본값 수정 |
| mood 기본값 블록 밖으로 이동 | `chunker.py:304` | extended=False 시에도 mood 보장 |
| TTS .mp3 하드코딩 → TTS_OUTPUT_FORMAT | `processor.py:345,351` | wav/mp3 포맷 설정 기반 |
| 댓글 author 누락 | `handlers.py:37` | generate_script 댓글에 닉네임 포함 |
| render_final_video 없음 (HD_RENDER 항상 실패) | `composer.py` | 함수 추가 |
| /api/settings/health 없음 | `SettingsController.java` | 헬스체크 엔드포인트 추가 |
| LlmLog 복합 필터 조기 return | `LlmLogController.java` | JPA Specification으로 교체 |
| Editor mood 드롭다운 | `editor/[postId]/page.tsx` | 9종 Select 드롭다운 |

추가: `types/index.ts` Mood 타입 추가, `LlmLogRepository` JpaSpecificationExecutor 확장, stale 코멘트 수정

## 2. 주요 수정 상세

### SceneDirector mood 미전달 (3곳)
- `SceneDirector.__init__`의 `mood` 파라미터 기본값 "daily" → 명시 전달 없이는 항상 daily BGM/스타일 적용
- `content_processor.py:99`: `mood=script.get("mood", "daily")` 추가
- `processor.py:144` (process_with_retry): `mood=script.mood` 추가
- `processor.py:845` (render_stage): `mood=script.mood` 추가

### _MOOD_TO_STYLE 매핑 불완전 (2곳)
- `processor.py`의 render_stage에 레거시 4개 mood만 있어 9개 신규 mood가 모두 "dramatic" fallback
- process_with_retry와 render_stage 양쪽 모두 9종 full 매핑으로 확장

### 기본 mood "funny" → "daily"
- `processor.py:769` llm_tts_stage의 ScriptData 생성 시 `mood=_raw.get("mood", "funny")`
- "funny"는 레거시 이름 — `"daily"`로 수정

### LlmLog 복합 필터 (조기 return 패턴 제거)
- 기존: `if callType: return` → `if postId: return` 순차 조기 return — callType+success 동시 필터 불가
- `LlmLogRepository`에 `JpaSpecificationExecutor<LlmLog>` 추가
- 컨트롤러에서 JPA Criteria API로 교체 — 모든 파라미터 AND 복합 필터 지원

### render_final_video 없음 (HD_RENDER 항상 실패)
- `handlers.py`가 `from ai_worker.renderer.composer import render_final_video` 호출
- `composer.py`에 해당 함수 없어 모든 HD_RENDER 작업이 `ImportError`로 실패
- `Content.summary_text`에서 ScriptData 복원 후 `render_layout_video()` 호출하는 함수 추가

### /api/settings/health 없음
- 설정 페이지 LLM 헬스체크가 404 → 항상 "error" 표시
- CLI 백엔드: `llm-worker:8090/actuator/health` 프로브
- API 백엔드: `credentials.json`의 `anthropic_api_key` 존재 여부 확인

## 3. 수동 테스트 방법

```
1. 게시글 1건 승인 → HD_RENDER 작업 실행
   → 이전: ImportError 실패
   → 이후: 정상 렌더링

2. 설정 페이지 → "LLM 연결 확인" 버튼 클릭
   → CLI 백엔드: llm-worker 연결 상태 표시
   → API 백엔드: API 키 설정 여부 표시

3. use_content_processor=true 설정 후 게시글 처리
   → ai_worker 로그에서 mood가 "daily" 이외 값 확인
   → SceneDirector가 올바른 mood BGM/이미지 선택 확인

4. LLM 로그 페이지: callType + success 동시 필터 동작 확인

5. editor 페이지 mood 드롭다운 동작 확인
```

## 4. 추천 commit message

```
fix: render_stage mood 미전달 3곳, _MOOD_TO_STYLE 9종 확장, LlmLog 복합 필터, HD_RENDER
```
