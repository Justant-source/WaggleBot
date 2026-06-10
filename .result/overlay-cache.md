# 오버레이 캐시 구현 결과

## 1. 작업 결과

`_render_video_text_overlay` 함수에 process 내 유효한 MD5 해시 기반 캐시를 추가했습니다.
동일한 (text, 자막 스타일, 캔버스 크기, 출력 포맷) 조합이 반복 호출될 경우 PIL 렌더링을
건너뛰고 `shutil.copy2`로 PNG를 복사만 수행합니다. 렌더링 결과는 일체 변경 없습니다.

---

## 2. 수정 내용

### `worker/ai_worker/renderer/_frames.py`

**추가 import (1줄):**
```python
import shutil
```

**모듈 레벨 캐시 dict 추가 (logger 바로 아래):**
```python
_overlay_cache: dict[str, Path] = {}
```

**`_render_video_text_overlay` 함수 수정:**

캐시 키 구성 요소:
- `text` — 자막 텍스트 전문
- `layout["scenes"]["video_text"]` — font_size, color, stroke, max_width, y 좌표 등 자막 스타일 전체
- `canvas.width x canvas.height` — 캔버스 크기
- `out_png.suffix` — 출력 포맷 (`.png`)

동작 흐름:
1. 위 4가지를 `|` 구분자로 이어 붙인 뒤 MD5 hexdigest 계산
2. `cache_key in _overlay_cache` AND 캐시 파일이 실제 존재(`Path.exists()`) 시:
   - 캐시 경로 ≠ `out_png`이면 `shutil.copy2(cached, out_png)`
   - 즉시 `out_png` 반환 (PIL 렌더링 완전 스킵)
3. 미스 시: 기존 렌더링 로직 그대로 실행 후 `_overlay_cache[cache_key] = out_png` 저장
4. 히트/미스 모두 `logger.debug` 로그 추가

---

## 3. 테스트 결과물 저장 위치

- 캐시는 메모리(`_overlay_cache` dict)에만 존재 — 디스크 별도 저장 없음
- 렌더링 PNG 출력 경로: 기존과 동일 (`media/` 하위 씬별 세그먼트 경로)

---

## 4. 수동 테스트 방법

```bash
# ai_worker 실행 중 debug 로그 확인
docker compose -f env/docker-compose.yml logs --tail 100 ai_worker | grep -E "오버레이 캐시"
# 첫 번째 씬: "오버레이 캐시 저장 (key=XXXXXXXX…): overlay_scene_1.png"
# 동일 자막 씬: "오버레이 캐시 히트 → overlay_scene_3.png (from overlay_scene_1.png)"
```

동일 자막 텍스트가 반복되는 영상에서 히트율 확인:
- 테스트 영상에서 "좋아요 구독" 같은 반복 자막이 다수인 경우 히트 로그 다수 출력 예상

캐시 비활성화 없이 레이아웃 변경 반영 확인:
- `config/layout.json`의 `video_text` 섹션 수정 → 동일 텍스트라도 캐시 미스 (스타일 변경이 해시에 반영)

---

## 5. 추천 commit message

```
perf: _render_video_text_overlay MD5 해시 캐시 추가 (process 내 PNG 재사용)

동일한 text + 자막 스타일 + 캔버스 크기 조합은 PIL 렌더링을 건너뛰고
shutil.copy2로 PNG 복사만 수행. 레이아웃 변경 시 자동으로 캐시 미스.
```
