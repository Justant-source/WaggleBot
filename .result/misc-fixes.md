# misc-fixes

## 1. 작업 결과

버그 7건 수정 (TTS 오독 방지, 마이그레이션 원자성, 프론트엔드 경쟁 조건, TTS 해시 충돌, subprocess 행, YouTube API null).

| 항목 | 파일 | 내용 |
|------|------|------|
| URL/이메일/해시태그 TTS 오독 | `tts/normalizer.py:236` | Fish Speech 전달 전 URL·이메일·해시태그 제거 |
| DDL 마이그레이션 부분 적용 리스크 | `migrations/runner.py:76` | DDL/tracking INSERT 분리 try-except + INSERT IGNORE |
| llm-logs 필터 변경 시 이중 API 호출 | `llm-logs/page.tsx:78` | `cancelled` 플래그로 stale 응답 폐기 |
| TTS 임시파일 hash 충돌 | `fish_client.py:190` | `hash()` → `hashlib.md5().hexdigest()[:16]` |
| intro 패딩 subprocess 무한 대기 | `renderer/_tts.py:99` | `timeout=30` 추가 |
| outro silence subprocess 무한 대기 | `renderer/_tts.py:115` | `timeout=10` 추가 |
| merge concat 파일 미정리 + 무한 대기 | `renderer/_tts.py:132` | try-finally + `timeout=120` |
| YouTube 통계 None → int 변환 실패 | `uploaders/youtube.py:167` | `or 0` 폴백 추가 |

## 2. 수정 상세

### TTS URL/이메일/해시태그 제거 (P1)
- 게시글 본문에 `https://example.com`, `user@email.com`, `#해시태그` 포함 시
  Fish Speech가 문자 단위로 읽거나 중국어 폴백 발음 → 어색한 TTS
- `normalize_for_tts()`의 숫자 변환 이후, 특수문자 정리 이전에 3개 regex 삽입
- `re` 모듈은 이미 import되어 있어 의존성 추가 없음

### DDL 마이그레이션 원자성 (P1)
- MariaDB에서 `ALTER TABLE`은 DDL auto-commit → rollback 불가
- 기존 코드: DDL 성공 후 `schema_migrations` INSERT 실패 시 `rollback()` 호출 (DDL 되돌리기 불가) → 다음 실행에서 DDL 재시도 → "duplicate column" 에러 무한 반복
- 수정: DDL과 tracking INSERT를 별도 try-except 블록으로 분리
- `INSERT IGNORE` 사용: 재실행 시 tracking INSERT 중복 키 에러 방지
- INSERT 실패 시 수동 복구 명령을 에러 로그에 명시

### llm-logs 필터 이중 요청 (P1)
- 필터 변경 + page > 0 상황: Effect 1 (`setPage(0)`) → Effect 2 두 번 실행
  (첫 번째: 이전 page로 API 호출, 두 번째: page=0으로 호출)
- 첫 번째 요청 응답이 두 번째보다 늦게 도착하면 stale 데이터 표시
- `cancelled` 클로저 플래그: cleanup 시 `cancelled=true` → stale 응답은 setState 생략
- Effect 1에서 `setLoading(true)` 제거 (Effect 2가 실제 로딩 시작점)

## 3. 수동 테스트 방법

```
1. TTS 오독 수정:
   게시글 body에 URL("https://naver.com") 포함 후 대본 생성 + TTS 실행
   → URL 부분 발음 없이 건너뜀 확인

2. 마이그레이션 원자성:
   migrations/ 디렉토리에 새 SQL 추가 후 runner 실행 중단 (Ctrl+C)
   → 재실행 시 INSERT IGNORE로 정상 진행 확인

3. llm-logs 필터 경쟁 조건:
   llm-logs 2페이지 이동 → callType 필터 변경
   → 브라우저 네트워크 탭: 2번 API 호출 중 첫 번째 응답 무시 확인
   → 최종 표시 데이터: 새 필터 page=0 결과만 표시
```

### TTS hash 충돌 (P1)
- `output_path=None`일 때 `hash(text)` 사용 → Python 3.3+ hash randomization으로 실행마다 다름
- 동일 텍스트가 다른 프로세스에서 다른 경로로 캐시되면 재사용 불가
- 동시 호출(동일 텍스트)은 같은 경로에 쓰기 → 파일 손상 가능
- `hashlib.md5(text.encode()).hexdigest()[:16]`으로 결정론적 해시 사용

### subprocess timeout (P1)
- `_tts.py`의 3개 ffmpeg 호출에 timeout 없음 → fish-speech 응답 없음 + ffmpeg 행 시 렌더링 영구 블록
- intro 패딩: 30초, outro 무음: 10초, TTS merge concat: 120초 (씬 수에 따라 길 수 있음)
- concat 파일: subprocess 실패 시 except로 건너뛰어 임시 파일 남음 → try-finally로 항상 삭제

### YouTube 통계 None (P2)
- 새로 업로드된 영상은 statistics 필드가 null일 수 있음 → `int(None)` → TypeError
- `stats.get("viewCount") or 0` 패턴으로 None/빈문자열 모두 0으로 처리

## 4. 수동 테스트 방법

```
1. TTS 오독 수정:
   게시글 body에 URL("https://naver.com") 포함 후 대본 생성 + TTS 실행
   → URL 부분 발음 없이 건너뜀 확인

2. 마이그레이션 원자성:
   migrations/ 디렉토리에 새 SQL 추가 후 runner 실행 중단 (Ctrl+C)
   → 재실행 시 INSERT IGNORE로 정상 진행 확인

3. llm-logs 필터 경쟁 조건:
   llm-logs 2페이지 이동 → callType 필터 변경
   → 최종 표시 데이터: 새 필터 page=0 결과만 표시

4. TTS hash 중복: 동일 텍스트 TTS 두 번 → 같은 경로에 저장 확인

5. subprocess 행: ffmpeg 제거 후 렌더링 → TimeoutExpired 예외로 정상 실패
```

## 5. 추천 commit message

```
fix: TTS URL 오독, subprocess timeout, hash 충돌, migration DDL 원자성, llm-logs 경쟁 조건
```
