# GPU 효율 개선 P2 결과

## 1. 작업 결과

Phase 7 진입 전 동적 VRAM 경고 및 ComfyUI 워크플로 JSON 캐싱, 두 가지 P2 GPU 효율 개선을 구현했습니다.

| 개선 항목 | 효과 |
|---|---|
| Phase 7 동적 VRAM 경고 | 가용 VRAM < 13GB 시 OOM 위험을 미리 로그로 포착, 파이프라인은 계속 실행 |
| 워크플로 JSON 캐싱 | 씬마다 반복되던 디스크 I/O 제거 — 동일 워크플로 파일은 프로세스 수명 중 1회만 읽음 |

---

## 2. 수정 내용

### `worker/ai_worker/pipeline/content_processor.py`

**위치:** Phase 7 진입부 (`_clear_vram_for_video()` 및 설정 import 이후, `ComfyUIClient` 생성 이전)

**추가된 블록:**
```python
from ai_worker.core.gpu_manager import GPUMemoryManager
available_vram = GPUMemoryManager.get_system_available_vram()
if available_vram is not None and available_vram > 0 and available_vram < 13.0:
    logger.warning(
        "[content_processor] Phase 7 진입 경고: 가용 VRAM %.1fGB < 13GB. "
        "GGUF Q4 로드 중 OOM 발생 가능. 계속 진행합니다.",
        available_vram,
    )
else:
    logger.info(
        "[content_processor] Phase 7 진입 VRAM 확인: %.1fGB 여유",
        available_vram if available_vram else 0.0,
    )
```

- `GPUMemoryManager.get_system_available_vram()` — 이미 존재하는 `@staticmethod`. `nvidia-smi --query-gpu=memory.free` 기반 시스템 전체 여유 VRAM 반환 (MB → GB 변환). 실패 시 `0.0`.
- 임계값 13GB: GGUF Q4 UNet ~12.7GB + 소량 오버헤드를 고려한 최소 여유.
- 경고만 발생 — 파이프라인 중단 없음 (4단계 폴백이 OOM 복구 담당).
- `available_vram > 0` 조건으로 nvidia-smi 사용 불가 환경(0.0 반환)에서의 오탐 방지.

### `worker/ai_worker/video/comfy_client.py`

**추가된 모듈 레벨 요소:**
- `import copy` 추가
- `_workflow_cache: dict[str, dict] = {}` — 모듈 레벨 캐시
- `_load_workflow(path: str | Path) -> dict` — 캐싱 헬퍼 함수
  - 최초 접근 시 `Path.read_text()` + `json.loads()`로 파일 읽기
  - 이후 호출은 `copy.deepcopy(캐시[key])` 반환 (수정 방지)
  - `logger.debug`로 캐시 등록 시점 기록

**수정된 인스턴스 메서드 `_load_workflow`:**
```python
def _load_workflow(self, filename: str) -> dict:
    """workflows/ 디렉터리에서 워크플로우 JSON 로드 (모듈 캐시 사용)."""
    path = self._workflow_dir / filename
    return _load_workflow(path)
```
- 기존: `open(path) + json.load(f)` — 씬마다 디스크 I/O 발생
- 변경: 모듈 캐시 함수 위임 — 동일 파일은 1회만 읽음

**캐시 적용 범위:** `generate_t2v`, `generate_t2v_with_upscale`, `generate_i2v` 내 모든 `self._load_workflow(...)` 호출이 자동으로 캐시를 활용.

---

## 3. 테스트 결과물 저장 위치

- Phase 7 VRAM 경고 로그: `docker compose logs ai_worker | grep "Phase 7 진입"`
- 워크플로 캐시 로그: `docker compose logs ai_worker | grep "워크플로우 캐시 등록"`

---

## 4. 수동 테스트 방법

### 변경 1: Phase 7 동적 VRAM 경고

```bash
# ai_worker 로그에서 Phase 7 진입 VRAM 확인 메시지 검색
docker compose -f env/docker-compose.yml logs --tail 200 ai_worker | grep "Phase 7 진입"

# VRAM 여유 충분 시 예상 출력:
# [content_processor] Phase 7 진입 VRAM 확인: 15.3GB 여유

# VRAM 부족 시 예상 출력:
# WARNING [content_processor] Phase 7 진입 경고: 가용 VRAM 11.2GB < 13GB. GGUF Q4 로드 중 OOM 발생 가능. 계속 진행합니다.
```

### 변경 2: 워크플로 JSON 캐싱

```bash
# 최초 씬 처리 시 캐시 등록 로그 확인
docker compose -f env/docker-compose.yml logs --tail 200 ai_worker | grep "워크플로우 캐시 등록"
# 예상: DEBUG [comfy] 워크플로우 캐시 등록: t2v_ltx2.json

# 두 번째 씬부터는 캐시 등록 로그 없음 (캐시 히트)
```

---

## 5. 추천 commit message

```
perf: Phase7 진입 전 동적 VRAM 경고 + ComfyUI 워크플로 JSON 캐싱

- Phase 7 시작 전 nvidia-smi로 가용 VRAM 조회 → 13GB 미만 시 OOM 경고 로그
  (파이프라인 중단 없음, 4단계 폴백이 복구 담당)
- comfy_client.py에 모듈 레벨 _workflow_cache 추가, _load_workflow() 캐싱 헬퍼로
  씬마다 반복되던 디스크 I/O를 프로세스 수명 중 1회로 축소
```
