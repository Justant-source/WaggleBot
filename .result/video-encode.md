# 비디오 세그먼트 단일 NVENC 인코딩 결과

## 1. 작업 결과

`_render_video_segment`에서 LTX-2 클립을 처리할 때 발생하던 이중 NVENC 인코딩을 단일 FFmpeg 명령으로 통합했습니다. `resize_clip_to_layout` + `loop_or_trim_clip` 호출로 생성되던 `resized_*.mp4`, `fitted_*.mp4` 중간 파일이 제거되었습니다.

## 2. 수정 내용

### `worker/ai_worker/renderer/_encode.py`

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| `_get_encoder_args` preset | `"medium"` (NVENC 미지원 값) | `"p4"` (NVENC 동급 품질 프리셋) |
| `_render_video_segment` import | `resize_clip_to_layout`, `loop_or_trim_clip` import | 제거 |
| 중간 파일 | `resized_*.mp4`, `fitted_*.mp4` 생성 후 삭제 | 생성 없음 |
| FFmpeg 입력 | `fitted_clip` (재인코딩된 중간 파일) | `-stream_loop -1 -i {clip_path}` (원본 직접 demux 루프) |
| filter_complex | `[base][1:v]overlay` (이미 resize된 클립 사용) | `[1:v]scale+crop+fps[clip]; [base][clip]overlay` (단일 패스 통합) |
| `overlay shortest` | `shortest=1` | `shortest=0` (`-t`로 길이 제어) |
| 임시파일 정리 | `base_png`, `resized_clip`, `fitted_clip`, `text_overlay_png` | `base_png`, `text_overlay_png` (2개로 감소) |

**핵심 변경 — filter_complex:**
```
[0:v]loop=loop={frame_count}:size=1:start=0,setpts=N/30/TB,fps=30[base];
[1:v]scale={va_w}:{va_h}:force_original_aspect_ratio=increase,crop={va_w}:{va_h},fps=30[clip];
[base][clip]overlay={va_x}:{va_y}:shortest=0[vwith];
[2:v]scale={canvas_w}:{canvas_h}[txt];
[vwith][txt]overlay=0:0[vout]
```

### `worker/ai_worker/video/video_utils.py`

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| `_resolve_intermediate_codec` | `-preset p1` (CQ 미지정 → 가변 품질) | `-preset p1 -cq 30` (명시적 CQ 지정) |

`resize_clip_to_layout`, `normalize_clip_format` 함수 자체는 fallback/다른 경로에서 여전히 사용되므로 삭제하지 않았습니다.

## 3. 테스트 결과물 저장 위치

렌더링된 세그먼트 파일: `assets/media/tmp/seg_{stem}.mp4`

## 4. 수동 테스트 방법

1. `VIDEO_GEN_ENABLED=true` 환경으로 ai_worker 실행
2. video_mode가 `t2v` 또는 `i2v`인 씬이 있는 Content를 APPROVED 상태로 처리
3. ai_worker 로그에서 아래 확인:
   - `[layout] video_segment 생성: seg_*.mp4 (X.XXs)` 로그 1회만 출력 (이전에는 resize/loop 로그 먼저 2회 출력)
   - `resized_*.mp4`, `fitted_*.mp4` 임시파일이 tmp 디렉토리에 남지 않음
4. 최종 영상의 video_text 씬에서 클립이 정상 재생되는지 확인

```bash
docker compose -f env/docker-compose.yml logs --tail 50 ai_worker | grep -E "resize|loop_or_trim|video_segment"
```

## 5. 추천 commit message

```
perf: video_segment 이중 NVENC 인코딩 제거 → 단일 FFmpeg 패스 통합

- resize_clip_to_layout + loop_or_trim_clip 중간 파일 생성 단계 제거
- demux 레벨 -stream_loop + filter_complex scale/crop 통합으로 인코딩 1회로 감소
- _get_encoder_args preset "medium" → "p4" (NVENC 올바른 프리셋 네이밍)
- _resolve_intermediate_codec p1 프리셋에 -cq 30 추가 (fallback 경로 품질 안정화)
```
