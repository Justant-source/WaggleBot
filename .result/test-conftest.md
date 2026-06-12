# 테스트 수집 제외 + asyncio.run 버그픽스

## 1. 작업 결과

pytest auto-collection 시 라이브 네트워크 요청을 발생시키는 테스트 2종 추가 제외. `test_error_handling.py` main runner의 sync 함수 asyncio.run 오용 수정.

## 2. 수정 내용

### `worker/test/conftest.py`

```diff
+ # test_dc_images.py: def test_*() → bool 반환, DCInside 라이브 네트워크 요청 포함
+ # test_scene_director_dc_download.py: 동일 패턴, DC 이미지 다운로드 E2E
  collect_ignore = [
      "test_pipeline_phases.py",
      "test_fish_speech.py",
+     "test_dc_images.py",
+     "test_scene_director_dc_download.py",
  ]
```

두 파일 모두 `def test_*() -> bool:` 반환 구조 (pytest 스타일 아님). pytest 수집 시 함수가 실행되어 DCInside HTTP 요청 발생 → CI 환경에서 실패 또는 행업.

### `worker/test/test_error_handling.py`

```diff
  # 비동기 테스트
- asyncio.run(test_llm_error_no_retry())  # sync 함수 반환값(None)을 asyncio.run에 전달 → 오류
+ test_llm_error_no_retry()               # 내부에서 이미 asyncio.run 호출
```

`test_llm_error_no_retry()`는 sync 함수(내부에서 `asyncio.run(_async_...)` 호출). `asyncio.run(sync_fn())`은 `sync_fn()`의 반환값 `None`을 coroutine으로 전달하여 `TypeError: a coroutine was expected` 발생.

## 3. 테스트 결과물 위치

없음 (컨테이너 없이 정적 분석)

## 4. 수동 테스트 방법

```bash
# pytest 수집 확인 — dc_images, scene_director_dc_download 빠져있어야 함
docker compose -f env/docker-compose.yml exec ai_worker \
    python -m pytest test/ --collect-only 2>&1 | grep -E "dc_images|scene_director_dc"
# → 아무것도 출력되지 않으면 정상

# test_error_handling 직접 실행 확인
docker compose -f env/docker-compose.yml exec ai_worker \
    python test/test_error_handling.py
```

## 5. 추천 commit message

```
fix: pytest 수집 제외(DC 이미지 E2E 2종) + test_error_handling asyncio.run 오용 수정
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 (테스트 인프라 수정, docs 변경 없음)
