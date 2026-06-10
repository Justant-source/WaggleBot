# 실패 원인 UI 노출 구현 결과

## 1. 작업 결과

파이프라인 FAILED 상태 포스트의 오류 원인을 DB에 저장하고 대시보드 진행현황 페이지에 표시하는 기능을 풀스택(Python/Java/TypeScript)으로 구현했습니다.

## 2. 수정 내용

### DB 마이그레이션
| 파일 | 변경 |
|---|---|
| `worker/db/migrations/006_add_post_last_error.sql` | 신규 생성 — `posts.last_error VARCHAR(1000) NULL` 컬럼 추가 |

### Python (worker)
| 파일 | 변경 |
|---|---|
| `worker/db/models.py` | `Post.last_error = Column(String(1000), nullable=True)` 추가 (retry_count 아래) |
| `worker/ai_worker/core/main.py` | `_mark_post_failed(post_id, error="")` 시그니처 변경 + `post.last_error` 저장; LLM+TTS / 렌더링 실패 호출부에 `error=repr(exc)` 전달; 업로드 실패 경로 `last_error="업로드 실패"` 설정; `_recover_stuck_posts()`에서 복구 시 `last_error=None` 초기화 |
| `worker/ai_worker/core/processor.py` | `_mark_as_failed()` — `post.last_error = repr(last_error)[:1000]` 저장; `llm_tts_stage()` — PROCESSING 진입 시 `last_error=None` 초기화 |

### Java (backend)
| 파일 | 변경 |
|---|---|
| `backend/.../domain/Post.java` | `@Column(name="last_error", length=1000) private String lastError;` 필드 추가 (Lombok @Getter/@Setter로 자동 노출) |
| `backend/.../domain/PostRepository.java` | `findTop20ByStatusOrderByUpdatedAtDesc(PostStatus)` 메서드 추가 |
| `backend/.../controller/ProgressController.java` | `getProgress()` — `failed` 키에 최근 FAILED 포스트 최대 20건(`lastError` 포함) 반환 추가; `retry()` — `post.setLastError(null)` 추가 |

### TypeScript (frontend)
| 파일 | 변경 |
|---|---|
| `frontend/lib/types/index.ts` | `Post` 인터페이스에 `lastError?: string \| null` 추가 |
| `frontend/lib/api/progress.ts` | `get()` 반환 타입에 `failed: Post[]` 추가 |
| `frontend/app/(admin)/admin/progress/page.tsx` | `FailedPostCard` 컴포넌트 신규 추가 (제목 + 오류 접기/펼치기 + 재시도 버튼); `failed` 상태 추가; "실패 목록" 섹션을 실제 카드 UI로 교체 |

## 3. 테스트 결과물 저장 위치

없음 (UI 변경 — 런타임 테스트 필요)

## 4. 수동 테스트 방법

1. 마이그레이션 실행:
   ```bash
   docker compose exec dashboard python -m db.migrations.runner
   ```
2. ai_worker 재시작 후 의도적으로 실패하는 게시글(없는 이미지 URL 등) 처리
3. 대시보드 `/admin/progress` 접속 → "실패 목록" 섹션에 포스트 + 오류 메시지 카드 확인
4. "오류 펼치기" 클릭 → `repr(exc)` 형식 오류 텍스트 표시 확인
5. "재시도" 버튼 클릭 → 포스트가 APPROVED로 전환되고 목록에서 사라지는 것 확인

## 5. 추천 commit message

```
feat: 파이프라인 실패 원인 DB 저장 및 진행현황 UI 노출

- posts.last_error 컬럼 추가 (migration 006)
- _mark_post_failed/processor._mark_as_failed에 오류 문자열 저장
- ProgressController GET /api/progress에 failed 목록(최대 20건) 포함
- retry 시 last_error 초기화
- 진행현황 페이지 실패 목록에 오류 접기/펼치기 + 재시도 버튼 카드 UI
```
