# 렌더링 최적화 2종 결과

## 1. 작업 결과

P2 렌더링 최적화 2가지를 구현했습니다.

| 개선 항목 | 예상 효과 |
|---|---|
| ComfyUI 적응형 폴링 | 짧은 생성(30초 미만)은 1초 간격으로 빠른 감지, 긴 생성(2분 이상)은 5초로 폴링 부하 감소 |
| 렌더링 seg_*.mp4 즉시 삭제 | concat 완료 직후 세그먼트 파일 제거 → 임시 디스크 사용량 최대 N×세그먼트_크기만큼 절약 |

---

## 2. 수정 내용

### `worker/ai_worker/video/comfy_client.py`

**추가 import:** `time` (표준 라이브러리)

**신규 정적 메서드 `_adaptive_interval(elapsed_secs: float) -> float`:**
- 0 ≤ elapsed < 30초 → 1.0초
- 30 ≤ elapsed < 120초 → 3.0초 (기존 고정값과 동일)
- elapsed ≥ 120초 → 5.0초

**`_poll_until_done()` 시그니처 변경:**
- 파라미터 `interval: float = 3.0` 제거
- 루프 시작 전 `start_time = time.monotonic()` 기록
- `await asyncio.sleep(interval)` → `await asyncio.sleep(self._adaptive_interval(elapsed))`
  - `elapsed = time.monotonic() - start_time` 는 매 루프 반복 마지막에 계산

**`_queue_and_wait()` docstring 업데이트:**
- "polling (3초 간격)" → "polling (적응형 간격)" 으로 수정

### `worker/ai_worker/renderer/layout.py`

**`_render_pipeline()` 내 Step 9 (하이브리드 세그먼트 concat) 이후 삽입:**

```python
# concat 완료 후 세그먼트 파일 즉시 삭제 (디스크 절약)
for seg_path in segment_paths:
    seg_path.unlink(missing_ok=True)
logger.debug("[layout] seg_*.mp4 %d개 즉시 삭제 완료", len(segment_paths))
```

- `video_only.mp4` (concat 결과물)는 삭제하지 않음
- concat 실패 시 (`CalledProcessError` 발생) 삭제 코드에 도달하지 않으므로 안전
- `tmp_dir` 전체의 최종 `rmtree`(`finally` 블록)는 그대로 유지

---

## 3. 테스트 결과물 저장 위치

- 적응형 폴링: ComfyUI 생성 로그 (`docker compose logs ai_worker`)
- 세그먼트 삭제: `media/tmp/layout_{post_id}/` 내 `seg_*.mp4` 파일 — concat 후 즉시 없어짐

---

## 4. 수동 테스트 방법

### 변경 1: 적응형 폴링

```bash
# VIDEO_GEN_ENABLED=true 상태에서 단편 비디오 생성 시 로그 확인
docker compose -f env/docker-compose.yml logs --tail 200 ai_worker | grep "\[comfy\]"
# 30초 이내 완료 시: polling을 1초 간격으로 시작하고 짧게 완료되는 것 확인
# 2분 이상 걸리는 생성: 120초 경과 후 로그 빈도가 줄어드는 것 확인
```

### 변경 2: seg_*.mp4 즉시 삭제

```bash
# 하이브리드 렌더링(has_video_scenes=true) 시 tmp 디렉토리 모니터링
watch -n 1 'ls -lh /path/to/media/tmp/layout_*/seg_*.mp4 2>/dev/null | wc -l'
# concat 완료 직후 파일 수가 0으로 떨어지는지 확인
# video_only.mp4는 남아있어야 함:
ls /path/to/media/tmp/layout_*/video_only.mp4
```

---

## 5. 추천 commit message

```
perf: ComfyUI 적응형 폴링 + 렌더링 seg_*.mp4 즉시 삭제

- _adaptive_interval(): 경과 시간 기반 폴링 주기 자동 조정
  (0-30s=1초, 30-120s=3초, 120s+=5초)으로 짧은 생성 빠른 감지
- 하이브리드 렌더링 concat 완료 직후 seg_*.mp4 즉시 unlink
  (video_only.mp4 보존, finally rmtree는 유지)
```
