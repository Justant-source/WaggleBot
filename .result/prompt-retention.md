# 프롬프트 자극도/리텐션 강화 (6가지 추가)

## 1. 작업 결과

`client.py`의 `_SCRIPT_SYSTEM` 상수와 `chunker.py`의 `build_chunking_system()` 함수에
6가지 프롬프트 강화 내용을 동일하게 미러링했다.
JSON 스키마 구조(hook/body/closer/mood/tags/title_suggestion 필드), 캐시 prefix/suffix 분리,
파서 계약은 일체 변경하지 않았다.

## 2. 수정 내용

### (a) 나쁜 hook 예시 — Hook 규칙 끝에 추가

**client.py 삽입 위치:** 핵심 원칙 3 리텐션 섹션, 명사형 요약 금지 줄 직후 (원 44행 → 신 46~51행)
**chunker.py 삽입 위치:** `## 2. 리텐션 설계` 섹션, 후킹 공식 4번 줄 직후 (원 93행 → 신 95~100행)

추가된 내용:
- 4가지 절대 금지 패턴 + 구체 사유 명시
- 변환 예("남친 미행 후기" → "남친을 미행했는데, 도착한 곳이 모텔이 아니었다")

### (b) 무드별 중간 떡밥 — 단일 문구 → mood별 변주로 교체

**client.py:** 기존 `"근데 여기서부터가 진짜다" 같은 떡밥` 단일 예시 → mood 5개 그룹별 문구로 교체 (신 52~57행)
**chunker.py:** 기존 `"근데 진짜는 지금부터예요"` 단일 예시 → mood 5개 그룹별 문구로 교체 (신 101~106행)

mood 분기: shock/horror / humor / touching·sadness / anger·controversy / daily·info

### (c) 댓글 선택 전략 — 규칙 6 끝에 추가

**client.py:** 규칙 6 "베스트 댓글 필수 인용" 뒤에 4줄 추가 (신 103~107행)
**chunker.py:** `## 4. 블록·댓글·팩트 규칙`의 "입력에 베스트 댓글" 줄 직후에 5줄 추가 (신 122~126행)

역할 3분류(공감/정보보충/여운)와 closer 연계 배치 전략 포함.

### (d) 호칭 일관성 — 신규 규칙 추가

**client.py:** 규칙 7(어조·시점) 뒤에 규칙 8로 추가 (신 109~111행)
**chunker.py:** `## 4. 블록·댓글·팩트 규칙` 내 고유명사·팩트 줄 직후에 추가 (신 131~133행)

감정 전환 연출 목적 1회 예외 허용 조건 포함.

### (e) mood 판정 트리 — 단순 나열 → 우선순위 트리로 교체

**client.py:** 기존 규칙 8 "감정 분류: ... 중 가장 적합한 하나" → 규칙 9로 번호 변경 + 8단계 순서 트리로 교체 (신 112~120행). 기존 규칙 번호 9→10, 10→11, 11→12로 순차 재번호 처리.
**chunker.py:** 기존 단일 나열 줄 "mood는 humor|... 중 하나" → 8단계 순서 트리로 교체 (신 134~142행)

horror > shock > anger > touching/sadness > humor > controversy > info > daily 우선순위.

### (f) 리듬 O/X 예시 — 핵심 원칙 2(자연스러움) 섹션에 추가

**client.py:** 핵심 원칙 2의 "문장 길이와 리듬" 줄 직후에 2줄 추가 (신 36~37행)
**chunker.py:** `## 0. 자연스러움` 섹션의 "문장 길이와 리듬" 줄 직후에 2줄 추가 (신 75~76행)

X(균일 2줄 기계적) vs O(단문 툭 끊기+2줄 몰아치기로 긴장·이완 반복) 대조 예시.

### 파일별 수정 범위

| 파일 | 수정 전 행수 | 수정 후 행수 | 추가 행수 |
|------|------------|------------|---------|
| `worker/ai_worker/script/client.py` | 262행 | ~286행 | +24행 |
| `worker/ai_worker/script/chunker.py` | 288행 | ~313행 | +25행 |

## 3. 테스트 결과물 저장 위치

Python `ast` 구문 검사 통과 확인:
- `worker/ai_worker/script/client.py` → OK
- `worker/ai_worker/script/chunker.py` → OK

별도 산출 파일 없음. 런타임 검증은 아래 수동 테스트로 수행.

## 4. 수동 테스트 방법

```bash
# 1. 구문 검사 (호스트 가능)
python3 -c "
import ast
for p in ['worker/ai_worker/script/client.py','worker/ai_worker/script/chunker.py']:
    ast.parse(open(p).read()); print('OK:', p)
"

# 2. 대본 생성 통합 테스트 (컨테이너)
docker compose -f env/docker-compose.yml exec ai_worker \
  python worker/test/test_llm.py

# 3. 출력 확인 포인트
# - hook: 명사형 요약 없이 오픈루프/궁금증갭 형태인지
# - body: 단문-2줄 리듬 교차 있는지, 호칭 표류 없는지
# - 중간 떡밥: mood에 맞는 문구 사용됐는지 (고정 문구 반복 없는지)
# - comment: 역할 다른 3개 선택됐는지
# - mood: 판정 트리 순서 따른 값인지
```

## 5. 추천 commit message

```
feat: 프롬프트 자극도/리텐션 강화 6종 (client+chunker 미러링)

- (a) 나쁜 hook 금지 패턴 4가지 + 변환 예 추가
- (b) 중간 떡밥을 mood별 5그룹 변주 문구로 교체 (클리셰 고정 문구 제거)
- (c) 댓글 선택 전략: 역할 3분류(공감/정보/여운) + closer 연계 배치
- (d) 호칭 일관성 규칙 추가 (1회 예외 허용 조건 포함)
- (e) mood 판정을 단순 나열 → 8단계 우선순위 트리로 교체
- (f) 리듬 O/X 예시 추가 (균일 기계적 vs 긴장·이완 반복 대조)
- JSON 스키마/파서 계약·캐시 prefix 분리 구조 100% 보존
```
