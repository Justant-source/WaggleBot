# settings-ui

## 1. 작업 결과

Settings 페이지에 `pipeline.json`에 존재하던 두 필드(`upload_privacy`, `llm_prompt_cache`)를 UI에 노출했습니다.
ProgressController 재시도 엔드포인트의 비원자적 read-modify-write를 JPA `@Modifying @Query`로 교체했습니다.

| 항목 | 파일 | 내용 |
|------|------|------|
| `upload_privacy` UI | `settings/page.tsx` | 자동화 섹션 — `auto_upload=true`일 때 표시되는 공개범위 드롭다운 |
| `llm_prompt_cache` UI | `settings/page.tsx` | LLM 모델 섹션 — `llm_backend='api'`일 때 표시되는 프롬프트 캐시 토글 |
| ProgressController 원자적 retry | `ProgressController.java` + `PostRepository.java` | `setStatus/save` 2스텝 → `UPDATE ... SET status='APPROVED'` 단일 쿼리 |

## 2. 수정 내용

### settings/page.tsx
- `schema` + `defaultValues` + `setValue` + `save payload`에 `upload_privacy`, `llm_prompt_cache` 추가
- **upload_privacy Select**: `자동화` AdminSection 내 `auto_upload` Switch 아래에 추가. `autoUpload === true`일 때만 렌더. 기본값 `'unlisted'`
- **llm_prompt_cache Switch**: `LLM 모델` AdminSection 내 모델 오버라이드 아래에 추가. `llmBackend === 'api'`일 때만 렌더. 기본값 `true`

### PostRepository.java
```java
@Transactional
@Modifying
@Query("UPDATE Post p SET p.status = 'APPROVED', p.retryCount = p.retryCount + 1, p.lastError = NULL WHERE p.id = :id")
int resetForRetry(@Param("id") Long id);
```

### ProgressController.java
```java
@PostMapping("/{id}/retry")
public ResponseEntity<Map<String, Object>> retry(@PathVariable Long id) {
    int updated = postRepo.resetForRetry(id);
    if (updated == 0) throw new IllegalArgumentException("Post not found: " + id);
    return ResponseEntity.ok(Map.of("postId", id, "status", "APPROVED"));
}
```

## 3. 수동 테스트 방법

```
1. upload_privacy:
   설정 페이지 → 자동화 섹션 → 자동 업로드 ON
   → "업로드 공개 범위" 드롭다운 표시 확인
   → 값 변경 후 저장 → pipeline.json의 upload_privacy 반영 확인

2. llm_prompt_cache:
   설정 페이지 → AI 대본 생성 백엔드 → API 선택
   → LLM 모델 섹션에 "프롬프트 캐싱" 토글 표시 확인
   → CLI로 전환 시 토글 사라짐 확인

3. ProgressController atomic retry:
   FAILED 상태 포스트에 POST /api/progress/{id}/retry
   → Post status = APPROVED, retryCount +1 확인
   → 존재하지 않는 id → 400 에러 확인
```

## 4. 추천 commit message

```
fix: settings UI에 upload_privacy·llm_prompt_cache 노출, retry 원자적 쿼리 전환
```
