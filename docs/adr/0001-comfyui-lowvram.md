# ADR-0001: ComfyUI --lowvram 모드 고정

> **status:** accepted
> **date:** 2026-06-10
> **related:** docs/services.md (comfyui 섹션), CLAUDE.md (하드 제약)

## 컨텍스트

ComfyUI 기본 모드는 `--normalvram`이다. LTX-2 19B가 사용하는 Gemma-3-12B 텍스트 인코더는
BF16 기준 약 24GB VRAM을 요구한다. RTX 3090 (24GB)에서 `--normalvram`으로 실행 시
텍스트 인코딩 단계에서 OOM이 발생한다. Fish Speech TTS가 동시에 ~5GB를 점유하므로
여유 마진 없이 24GB를 초과한다.

## 결정

ComfyUI는 반드시 `--lowvram --reserve-vram 2 --fp8_e4m3fn-text-enc` 플래그로 실행한다.

| 플래그 | 효과 |
|--------|------|
| `--lowvram` | Gemma-3-12B 텍스트 인코더를 CPU로 오프로드 (~15GB VRAM 절약) |
| `--reserve-vram 2` | Fish Speech 동시 실행 시 2GB 안전 마진 확보 |
| `--fp8_e4m3fn-text-enc` | CPU 텍스트 인코더 FP8 양자화로 시스템 RAM 사용량 감소 |

## 결과

- Gemma 인코딩이 CPU에서 실행되므로 인코딩 속도가 느려진다 (씬당 ~10-30초 추가).
- OOM 없이 안정적으로 비디오를 생성할 수 있다.
- LTX-2 UNet (GGUF Q4, ~12.7GB)은 여전히 GPU에서 실행된다.
- Fish Speech와 ComfyUI가 동시에 실행 가능하다 (합계 ~17.7GB < 22GB 안전 영역).

## 금지사항

- `--normalvram` 사용 금지 — 텍스트 인코딩 OOM 발생 확인됨
- `--highvram` 사용 금지 — 메모리 요구량이 더 높아짐
- 27GB FP8 full checkpoint 사용 금지 — 시스템 RAM 17GB 부족으로 로딩 불가
- GGUF 대신 FP8 UNet 사용 금지 — 같은 이유
