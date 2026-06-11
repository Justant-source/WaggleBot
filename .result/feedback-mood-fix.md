# feedback-mood-fix

## 1. 작업 결과

`analytics/feedback.py`의 mood_weights 기본값과 LLM 프롬프트가 레거시 mood 키를 사용해 피드백 루프의 mood 힌트가 누락되던 문제 수정.

## 2. 수정 내용

**파일:** `worker/analytics/feedback.py`

- `_FEEDBACK_DEFAULTS.mood_weights`: `shocking/funny/serious/heartwarming` → 현재 9-mood 시스템 `humor/touching/anger/sadness/horror/info/controversy/daily/shock`
- `_STRUCTURED_PROMPT` 출력 형식의 mood_weights 예시도 동일하게 갱신 — LLM이 현재 mood 키로 응답하도록 유도

**영향:** `processor.py`가 `mood_weights`에서 가중치 1.1 초과 mood를 선호 힌트로 주입하는 로직이 이제 현재 mood 키와 매칭됨.

## 3. 테스트 결과

수동 확인: `feedback.py`의 `_FEEDBACK_DEFAULTS` 9-mood 키 일치, `_STRUCTURED_PROMPT` 프롬프트 동기화.

## 4. 수동 테스트 방법

```python
from analytics.feedback import _FEEDBACK_DEFAULTS
print(list(_FEEDBACK_DEFAULTS['mood_weights'].keys()))
# ['humor', 'touching', 'anger', 'sadness', 'horror', 'info', 'controversy', 'daily', 'shock']
```

## 5. 추천 commit message

```
fix: feedback 피드백 mood_weights 레거시 키 → 9-mood 시스템으로 교체
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음
