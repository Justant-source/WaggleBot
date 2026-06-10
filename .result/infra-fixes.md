# infra-fixes

## 1. 작업 결과

운영 안정성·품질 개선 6건 수정 (backend Java + Python 워커 + 프론트 인프라).

| 항목 | 파일 | 내용 |
|------|------|------|
| nul 파일 삭제 + gitignore | `.gitignore` | WSL `> nul` 리다이렉트 사고 파일 제거, 재발 방지 규칙 추가 |
| HD 렌더 중복 Job 방지 | `GalleryController.java` + `JobService.java` + `JobRepository.java` | PENDING/IN_PROGRESS HD_RENDER Job 존재 시 신규 생성 없이 기존 jobId 반환 |
| mood_weights 피드백 주입 | `processor.py` | feedback_config의 mood_weights(>1.1) → extra_instructions에 선호 mood 힌트 추가 |
| ComfyUI 워크플로우 mtime 캐시 | `comfy_client.py` | 파일 변경 시 자동 캐시 무효화 (프로세스 재시작 불필요) |
| implementation-status.md 현행화 | `docs/implementation-status.md` | 버그 픽스 이력 + 장기 개선 후보 목록 추가 |

## 2. 수정 상세

### HD 렌더 중복 방지 (P1)
- `GalleryController.hdRender()`: Job 생성 전 `jobService.findActiveJob()` 호출
- PENDING 또는 IN_PROGRESS 상태의 동일 postId HD_RENDER Job이 있으면 그 jobId를 `alreadyQueued: true`와 함께 반환
- `JobRepository`에 `findTopByPostIdAndJobTypeAndStatusInOrderByCreatedAtDesc()` 추가
- `JobService`에 `findActiveJob()` 위임 메서드 추가

### mood_weights 피드백 주입 (P1)
- `feedback_config.json`의 `mood_weights`에서 가중치 > 1.1인 mood를 최대 3개 추출
- "성과 분석 기반 선호 mood: humor, shock." 형태로 extra_instructions에 append
- 기존 `extra_instructions` 없으면 단독으로 설정, 있으면 줄바꿈 후 추가
- A/B 변형 설정이 있으면 여전히 variant_config가 우선됨 (기존 로직 유지)

### ComfyUI 워크플로우 mtime 캐시 (P2)
- 기존: 첫 로드 후 영구 캐시 (파일 수정해도 프로세스 재시작 전까지 반영 안 됨)
- 수정: `_workflow_mtime` dict로 파일 mtime 추적, 변경 시 자동 갱신
- 개발 중 워크플로우 수정 테스트 사이클 단축

## 3. 수동 테스트 방법

```
1. HD 렌더 중복 방지:
   갤러리에서 HD 렌더 클릭 → Job 생성 확인
   → 즉시 다시 클릭 → 같은 jobId + alreadyQueued:true 반환 확인
   (브라우저 네트워크 탭에서 응답 본문 확인)

2. mood_weights 주입:
   feedback_config.json에 "mood_weights": {"humor": 1.5, "shock": 1.3} 설정
   → 대본 생성 실행 → llm-logs에서 prompt_text에 "선호 mood: humor, shock" 포함 확인

3. ComfyUI 캐시 갱신:
   t2v_ltx2_distilled.json 수정 → ai_worker 로그에서 "캐시 등록/갱신" 메시지 확인
   (프로세스 재시작 없이)
```

## 4. 추천 commit message

```
fix: HD 렌더 중복 방지, mood_weights 피드백 주입, ComfyUI 워크플로우 캐시 mtime 갱신
```
