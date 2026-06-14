# ADR-0003: Phase 5(TTS) + Phase 6(video_prompt) asyncio.gather 병렬 실행

> **status:** accepted
> **date:** 2026-06-10
> **related:** worker/ai_worker/pipeline/content_processor.py, docs/pipeline.md

## 컨텍스트

`VIDEO_GEN_ENABLED=true` 시 Phase 5(TTS 생성)와 Phase 6(영어 프롬프트 변환)이
순차적으로 실행됐다. Phase 6은 haiku LLM 원격 호출로 씬 20개 기준 30~90초가 소요됐다.
이 대기 시간이 Phase 5 TTS에 직렬로 추가되어 전체 처리 시간이 불필요하게 늘어났다.

## 결정

Phase 5와 6을 `asyncio.gather`로 병렬 실행한다.

두 Phase가 접근하는 SceneDecision 필드가 완전히 분리되어 있어 안전하다:
- Phase 5: `scene.text_lines[j] = {"text": ..., "audio": ...}` 만 변경
- Phase 6: `scene.video_prompt` 만 변경

```python
(tts_ok, tts_fail), scenes = await asyncio.gather(
    _run_tts_phase(scenes),
    _run_phase6(),   # run_in_executor로 sync 래핑
)
```

Phase 6은 원격 haiku 호출만 수행하므로 GPU 충돌이 없다.
`VIDEO_GEN_ENABLED=false`일 때는 Phase 6이 스킵되어 기존 순차 흐름이 유지된다.

## 결과

씬 20개 기준 haiku 30~90초 대기가 TTS 시간 안에 숨는다.
전체 파이프라인 처리 시간이 `VIDEO_GEN_ENABLED=true` 시 유의미하게 단축된다.

## 금지사항

- Phase 5와 6을 다시 순차 실행으로 되돌리지 말 것
- GPU를 접촉하는 Phase (Phase 7 video_clip 생성)를 이 병렬 구조에 포함하지 말 것 — VRAM 충돌 위험
- Phase 5와 6이 같은 scene 필드를 쓰도록 수정하지 말 것 — 동시성 안전성이 깨짐
