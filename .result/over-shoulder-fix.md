# over-shoulder-fix

## 1. 작업 결과

`prompt_engine.py` PERSON FALLBACK 지시에서 over-shoulder 극전경 회피 추가.
`prompt-upgrade.md`의 "남은 개선 후보" — E2E에서 씬 0 클립이 over-shoulder 구도일 때 distilled 8-step이 전경 얼굴을 만화풍으로 렌더하는 현상을 제거.

## 2. 수정 내용

### `worker/ai_worker/video/prompt_engine.py`

**PERSON FALLBACK 수정 (L70-74):**
- 기존: 감정 씬에 "side profiles or over-shoulder angles" 권장
- 변경: "side profiles or two-shot (both subjects in frame)" 권장 + "avoid over-shoulder shots where a face fills the extreme foreground — distilled 8-step renders that as cartoon-like" 명시

**`_SHOT_TYPES` 추가 (L265):**
- "two-shot" 추가 — 생성 프롬프트에서 추출 가능하도록 (다음 씬 프레이밍 다양화 추적)

## 3. 테스트 결과물 위치

PERSON FALLBACK은 LLM에 전달되는 정적 텍스트이므로 단위 테스트가 없음.
기존 203 passed 유지 (변경이 검증 로직·스키마·외부 계약에 비침투적).

## 4. 수동 테스트 방법

파이프라인 E2E로 인물이 등장하는 감정 씬(touching/sadness/anger) 게시글 처리 후
생성된 T2V 프롬프트에서 "over-shoulder"가 없어지고 "two-shot" 또는 "side profile"이
우세해지는지 LLMLog로 확인.

## 5. 추천 commit message

```
fix: T2V 프롬프트 over-shoulder 극전경 회피 — distilled 만화풍 렌더 방지
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 (프롬프트 텍스트 조정, docs에 미기록 수준)
