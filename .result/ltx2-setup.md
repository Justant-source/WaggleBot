# LTX-2 비디오 생성 설정 완료

## 1. 작업 결과

ComfyUI LTX-2 19B distilled 모델을 사용한 비디오 클립 생성 파이프라인 전체 구동 성공.

- **post_id=6** 8-Phase 파이프라인 완료 → `PREVIEW_RENDERED`
- Phase 7: T2V 클립 5개 생성 성공 (씬당 197~246초)
- Phase 8: 최종 렌더링 `post_375454020_SD.mp4` (1080×1920, h264, 36.8초, 30fps)

## 2. 수정 내용

### 2-1. kornia `pad` ImportError 수정
**파일**: `/comfyui/custom_nodes/ComfyUI-LTXVideo/pyramid_blending.py` (컨테이너 내)

kornia 0.8.3에서 `pad`가 제거됨. `pad` import를 제거하고 `F.pad()` (torch.nn.functional)로 대체.

```python
# Before
from kornia.geometry.transform.pyramid import (..., pad,)
pad(image, ...)

# After
from kornia.geometry.transform.pyramid import (PyrUp, build_laplacian_pyramid, ...)
F.pad(image, ...)
```

### 2-2. 모델 다운로드
**위치**: `checkpoints/` 디렉토리 (Docker volume 마운트)

| 파일 | 크기 | 경로 |
|------|------|------|
| `ltx-2-19b-distilled_Q4_K_M.gguf` | 12.7GB | `checkpoints/diffusion_models/` |
| `LTX2_video_vae_bf16.safetensors` | 2.4GB | `checkpoints/vae/` |
| `ltx-2-19b-embeddings_connector_distill_bf16.safetensors` | 2.9GB | `checkpoints/ltx-2/` → ComfyUI `models/checkpoints/` |
| `gemma-3-12b-it-qat-q4_0-unquantized/` | ~15GB | `checkpoints/text_encoders/` |

HF source:
- GGUF/VAE/Connector: `Kijai/LTXV2_comfy`
- Gemma: `google/gemma-3-12b-it-qat-q4_0-unquantized`

27GB FP8 distilled 풀 체크포인트는 시스템 RAM(17GB) 부족으로 사용 불가 → Kijai의 pre-extracted connector 파일(2.9GB)로 대체.

### 2-3. 워크플로우 JSON 수정
**파일**: `worker/ai_worker/video/workflows/t2v_ltx2_distilled.json`, `i2v_ltx2_distilled.json`

- `ltxv_path`: `ltx-2-19b-distilled-fp8.safetensors` → `ltx-2-19b-embeddings_connector_distill_bf16.safetensors`
- LoraLoader 노드 제거 (LoRA 불필요, VRAM 절약)
- clip/model 참조 업데이트 (LoraLoader 제거로 인한 연결 수정)

### 2-4. AV prefix 감지 로직 패치 (핵심 버그픽스)
**파일**: `/comfyui/custom_nodes/ComfyUI-LTXVideo/embeddings_connector.py`, `text_embeddings_connectors.py` (컨테이너 내)

**문제**: connector 파일은 `model.diffusion_model.video_embeddings_connector.*` 키를 사용하는 AV 타입이지만, 코드가 AV 판별을 `audio_adaln_single.linear.weight` 존재 여부로만 판단 (풀 모델에만 존재 → connector 파일에 없음). 결과적으로 `embeddings_connector.` prefix 사용 → sd_connector 비어있어 `None` 반환 → `'NoneType' object is not callable` 에러.

**수정** (`embeddings_connector.py`):
```python
# Before
prefix = (
    av_connector_prefix
    if f"{_PREFIX_BASE}audio_adaln_single.linear.weight" in sd
    else video_only_connector_prefix
)

# After
_is_av_sd = (
    f"{_PREFIX_BASE}audio_adaln_single.linear.weight" in sd
    or any(k.startswith(av_connector_prefix) for k in sd)
)
prefix = av_connector_prefix if _is_av_sd else video_only_connector_prefix
```

**수정** (`text_embeddings_connectors.py`):
```python
# Before
is_av = f"{_PREFIX_BASE}audio_adaln_single.linear.weight" in sd

# After
_audio_connector_prefix = f"{_PREFIX_BASE}audio_embeddings_connector."
is_av = (
    f"{_PREFIX_BASE}audio_adaln_single.linear.weight" in sd
    or any(k.startswith(_audio_connector_prefix) for k in sd)
)
```

## 3. 테스트 결과물

- **최종 영상**: `/app/media/video/nate_pann/post_375454020_SD.mp4`
  - 포맷: h264 1080×1920 30fps, AAC 44100Hz, 36.8초
- **비디오 클립 5개**: `/app/media/tmp/videos/` (ComfyUI output 볼륨 공유)
- **post_id=6 DB 상태**: `PREVIEW_RENDERED`, `last_error=NULL`

## 4. 수동 테스트 방법

```bash
# 상태 확인
docker compose -f env/docker-compose.yml exec -T db mariadb -uwagglebot -pwagglebot wagglebot \
  -e "SELECT id, status, last_error FROM posts WHERE id=6;"

# 영상 스펙 확인
docker compose -f env/docker-compose.yml exec -T ai_worker \
  ffprobe -v quiet -show_streams /app/media/video/nate_pann/post_375454020_SD.mp4

# 새 포스트로 E2E 재실행 (post APPROVED 상태로 변경)
docker compose -f env/docker-compose.yml exec -T db mariadb -uwagglebot -pwagglebot wagglebot \
  -e "UPDATE posts SET status='APPROVED', last_error=NULL WHERE id=<POST_ID>;"
```

**주의**: ComfyUI 컨테이너 재빌드 시 `pyramid_blending.py` 및 `embeddings_connector.py`, `text_embeddings_connectors.py` 패치가 사라짐 → 재적용 필요. 영속화를 위해 컨테이너 이미지를 커밋하거나 Dockerfile에 패치를 포함할 것.

## 5. 추천 commit message

```
fix: ComfyUI LTX-2 distilled 비디오 생성 완전 구동

- pyramid_blending.py: kornia 0.8.3 pad 제거 → F.pad() 대체
- t2v/i2v_ltx2_distilled.json: fp8→connector 파일, LoRA 노드 제거
- embeddings_connector.py: AV prefix 감지 로직 수정 (connector-only 파일 지원)
- text_embeddings_connectors.py: is_av 판별 audio_embeddings_connector prefix 추가 감지
- 모델: GGUF Q4(12.7GB) + VAE(2.4GB) + connector(2.9GB) + Gemma-3-12B(15GB)
```
