# ADR-0002: 렌더러 단일 NVENC 인코딩 (filter_complex 통합)

> **status:** accepted
> **date:** 2026-06-10
> **related:** worker/ai_worker/renderer/_encode.py, CLAUDE.md (하드 제약)

## 컨텍스트

개선 전 `_encode.py`는 씬 처리 시 3단계 NVENC 인코딩을 수행했다:

1. `resize_clip_to_layout` — NVENC 1차 인코딩 (비트레이트 기아 가능)
2. `loop_or_trim_clip` — NVENC 2차 인코딩 (길이 조정)
3. `filter_complex` 오버레이 합성 — NVENC 3차 인코딩

각 중간 파일이 품질 손실을 누적했고, 씬당 20-30% 처리 시간이 낭비됐다.

## 결정

단일 FFmpeg 명령으로 resize/loop/trim/overlay를 `filter_complex`에서 동시 처리하고
NVENC 인코딩을 1회만 수행한다.

핵심 구조:
```
ffmpeg -y
  -i base.png
  -stream_loop -1 -i clip.mp4        # demux 레벨 루프 (비트스트림 재인코딩 없음)
  -i txtoverlay.png
  -filter_complex
    "[0:v]loop=...[base];
     [1:v]scale=W:H,crop=W:H,fps=30[clip];
     [base][clip]overlay=X:Y[vwith];
     [2:v]scale=CW:CH[txt];
     [vwith][txt]overlay=0:0[vout]"
  -map [vout] -t {duration}
  -c:v h264_nvenc -preset p4 -cq 23 -r 30 -an
```

`-stream_loop -1`은 demux 레벨 루프이므로 원본 LTX 클립 비트스트림이 그대로 흐른다.
scale/crop/fps는 filter_complex에서 1회만 처리된다.

## 결과

- 중간 재인코딩이 없으므로 품질 손실 없음
- 씬당 처리 시간 ~20-30% 단축
- concat 단계는 `-c copy`로 유지 (추가 재인코딩 없음)

## 금지사항

- `resize_clip_to_layout` 또는 `loop_or_trim_clip`을 별도 인코딩 단계로 복원 금지
- 중간 파일에 `-c:v h264_nvenc` 적용 금지 (filter_complex 이전 단계)
- concat 단계에서 `-c:v` 재인코딩 지정 금지 — `-c copy` 유지
