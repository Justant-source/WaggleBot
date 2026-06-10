# renderer-fixes

## 1. 작업 결과

렌더러/파이프라인 버그 6건 수정 (Python 워커 + 프론트엔드).

| 항목 | 파일 | 내용 |
|------|------|------|
| TTS 캐시 JSONDecodeError 미처리 | `layout.py:359` | try-except + 파일 크기 검증 후 폴백 재생성 |
| 0-duration 프레임 concat 실패 | `layout.py:399` | TTS 실패 프레임 plan/durations 동시 필터링 |
| post None 검사 누락 (렌더 후 re-fetch) | `processor.py:159` | None 시 ValueError 발생 |
| post None 검사 누락 (실패 처리 경로) | `processor.py:492` | None 시 에러 로그 후 return |
| normalizer.py 상대 경로 | `normalizer.py:12` | `Path(__file__).resolve().parents[3]/config` 절대 경로 |
| 비디오 클립 체크포인트 크기 미검증 | `manager.py:139` | `.stat().st_size > 1_000_000` 추가 |
| usePollJob 타이머 누수 | `analytics/page.tsx:21` | useRef로 cleanup 보장 |

## 2. 주요 수정 상세

### TTS 캐시 손상 시 전체 렌더링 실패 (P0)
- `layout.py`에서 `durations.json` 로드 시 `json.loads()` 예외 미처리
- 부분 기록된 캐시 파일도 크기 검증 없이 복사 → merged_tts 불완전 복사 가능
- try-except 감싸기 + `merged_tts.stat().st_size > 0` + durations 비어있지 않은지 확인 후 캐시 사용

### 0-duration 프레임 (P0)
- TTS 청크 실패 시 `_tts_chunk_async`가 `0.0` 반환
- `layout.py`의 segment 생성 루프에 `dur=0.0`이 전달되면 FFmpeg `-t 0` → 빈 세그먼트 → concat 실패
- TTS 생성(캐시 로드/신규 생성) 완료 후 `dur <= 0.0` 프레임 일괄 제거

### Post None (P1)
- `session.expire_all()` 후 장시간 대기 중 외부에서 post 삭제 가능성
- `process_with_retry` (l.159): ValueError 발생으로 명확한 실패 처리
- `_mark_post_failed` (l.492): 로그 후 조용히 return (실패 마킹 자체가 실패한 것이므로)

### normalizer.py 경로 (P2)
- `Path("config/layout.json")` 상대 경로 → 실행 디렉토리에 따라 기본값으로 폴백
- `Path(__file__).resolve().parents[3] / "config" / "layout.json"` 절대 경로로 변경
- `worker/ai_worker/script/normalizer.py` → 3단계 상위 = `worker/` 루트

### 비디오 체크포인트 크기 검증 (P1)
- 부분 기록된 클립(0~1MB)이 캐시 히트로 처리되면 이후 concat에서 FFmpeg 에러
- `Path.exists()` → `exists() and stat().st_size > 1_000_000`

### usePollJob 타이머 누수 (P1)
- 페이지 이동 시 이전 interval이 취소되지 않아 네트워크 요청 누적
- `useRef`로 timer 관리, `useEffect` cleanup에서 자동 해제

## 3. 수동 테스트 방법

```
1. TTS 캐시 손상 테스트:
   durations.json을 빈 파일로 만들고 렌더링 시도
   → 이전: JSONDecodeError로 전체 실패
   → 이후: 캐시 무시하고 TTS 재생성 후 렌더링

2. 0-duration 프레임:
   Fish Speech 컨테이너 중지 후 렌더링 시도 (일부 청크 실패)
   → 이전: concat 시 빈 세그먼트로 FFmpeg 에러
   → 이후: 실패 프레임 제거 후 부분 렌더링

3. analytics 페이지: 인사이트 생성 → 즉시 다른 페이지 이동
   → 이전: 폴링 계속 실행 (네트워크 탭에서 확인)
   → 이후: cleanup에서 interval 해제
```

## 4. 추천 commit message

```
fix: TTS 캐시 손상 폴백, 0-duration 프레임 필터, post None 검사, 타이머 누수
```
