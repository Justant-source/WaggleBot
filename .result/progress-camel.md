# progress-camel

## 1. 작업 결과

`ProgressController`·`OverviewController`의 `parseProgress`가 Python snake_case 키를 그대로 반환해 TypeScript 프론트가 progress를 읽지 못하던 버그 수정.

`ProcessingCard`는 `progress.currentPhase`, `progress.phaseName`, `progress.scenesDone` 등 camelCase를 기대하지만, Python progress.py가 저장한 JSON은 `current_phase`, `phase_name`, `scenes_done` snake_case.

## 2. 수정 내용

두 컨트롤러(`ProgressController.java`, `OverviewController.java`)에 동일한 변환 메서드 추가:

```java
// parseProgress 내부 변경
Map<String, Object> raw = (Map<String, Object>) state.get("progress");
if (raw != null) return toCamel(raw);  // ← snake_case → camelCase

// 신규 헬퍼
private static Map<String, Object> toCamel(Map<String, Object> src) { ... }
private static String snakeToCamel(String s) { ... }
```

## 3. 영향

- `진행현황` 페이지 ProcessingCard에 현재 단계(Phase Stepper), 씬 진행률 표시
- `대시보드` 페이지 ProcessingCard 동일
- "응답 없음" 판정(`updatedAt > 15분`)도 camelCase 변환 후 올바르게 작동

## 4. 수동 테스트 방법

```
1. ai_worker에서 포스트 파이프라인 실행
2. /admin/progress 페이지 → ProcessingCard의 PhaseStepper에 현재 phase 강조 확인
3. Phase 7(비디오) 중 씬 진행률 바 표시 확인
```

## 5. 추천 commit message

```
fix: parseProgress snake_case → camelCase 변환 추가 (진행현황 Phase Stepper 수정)
```
