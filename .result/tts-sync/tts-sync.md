# TTS Sync 작업 결과

## 1. 작업 결과

- 통합 narrator WAV의 원문 줄별 실제 발화 시각을 faster-whisper 단어 타임스탬프로 정렬한다.
- 화면은 음성 타임라인과 별도로 구성한다. 첫 WAV의 native PCM lead를 측정해 부족분만 보충함으로써 첫 줄도 실제 첫 음절보다 약 150ms 먼저 보이고, 이후 줄은 다음 음성보다 150ms 먼저 나타난다.
- text_only의 편집실 사전 분할 줄은 한 번에 그리지 않고 한 줄씩 plan entry로 바꾼다. 세 줄이 누적되면 다음 줄에서 화면을 초기화한다.
- 문자 수 비율 분할과 narrator fade를 제거했다. narrator 조각은 실제 줄 경계에서만 잘라 원래 순서로 재결합한다.
- 마지막 댓글 발화 종료 뒤 기존 화면을 250ms 유지한 다음 클로징 텍스트를 표시한다. outro WAV의
  실제 선행 digital silence를 측정해 부족분만 prepend하여 첫 음절을 약 150ms 뒤에 두고, 발화 뒤
  500ms 여백을 적용한다.
- final mux에 `-t <audio duration> -shortest`를 적용하고 BGM 경로의 무한 `apad`를 제거해 #449의 마지막 프레임 연장을 막는다.
- static PNG concat은 terminal frame을 중복하지 않고 `tpad=stop_mode=clone:stop=-1`로 마지막 프레임을 유지한다. CFR 30fps와 final cap으로 video/audio stream duration 차이를 최대 1 frame으로 제한한다.

## 2. 수정 내용

- `config/settings.py`: 자연스러움 우선 TTS speed 1.1 및 alignment/lead/outro timing 설정 추가.
- `worker/ai_worker/core/processor.py`: TTS 디스크 캐시를 speed+`pp_v4` 키로 전환해 구 1.2배(`pp_v3`) WAV 재사용 차단.
- `config/settings.py` / `worker/ai_worker/tts/alignment.py`: faster-whisper import 전 HF Hub/Xet/XDG cache를 writable `WHISPER_DOWNLOAD_ROOT` 하위로 강제하고 Xet을 비활성화.
- `worker/ai_worker/tts/alignment.py`: faster-whisper 단어 타임스탬프를 원문 줄에 대응하는 정렬 모듈 추가.
- `worker/ai_worker/renderer/_tts.py`: 실제 발화 경계 기반 narrator 재사용, 첫 발화 lead, outro 휴지/tail 처리.
- `worker/ai_worker/renderer/layout.py`: audio/visual timeline 분리, 순차 3줄 reset, final duration cap.
- `worker/ai_worker/renderer/_encode.py`: static/hybrid segment CFR 출력으로 segment duration 유지.
- `backend/src/main/java/com/wagglebot/external/ExternalIngestService.java`: Again Spring solo/paired closing 문구 변경.
- `worker/test/test_tts_sync.py`: alignment, 150ms lead, 3줄 reset, outro pause/tail, final cap 단위 테스트.

## 3. 테스트 결과물 위치

- 단위 테스트: `worker/test/test_tts_sync.py`
- 실행: `PYTHONPATH=.:worker /tmp/waggle-tts-sync-MJLDYB/bin/python -m pytest -q worker/test/test_tts_sync.py worker/test/test_scene_idx_mapping.py`
- 결과: `23 passed` (narrator native 118ms→32ms만 보충, 이미 267.596ms면 무보충, outro -45 dBFS/3-frame debounce 측정, cache invalidation·HF/Xet cache 경로 및 static concat/tpad 회귀 검증 포함)
- static mux regression: 기존 isolated smoke는 audio `4.688844s` 대비 video stream `1.266667s`(38 frames)로 실패했다. terminal frame 중복 없이 `tpad=stop_mode=clone:stop=-1`을 적용한 원격 2-frame actual renderer smoke는 PASS: video `4.666667s`/140 frames @30fps, audio `4.688844s`, format `4.689s`, delta `22.177ms`(30fps 한 frame `33.333ms` 미만)이며 extra tail/early video end가 없었다.
- 백엔드 컴파일: `cd backend && ./gradlew compileJava` → PASS
- 원격 #449 real ASR smoke: PASS — narrator `31.122336s`, 26개 순차 줄, faster-whisper
  small/int8 CPU confidence `1.0`. starts: `[0.0, 2.3, 3.36, 4.1, 5.58, 6.5, 7.8, 8.66, 9.6,
  10.74, 11.92, 12.76, 14.22, 15.92, 16.66, 17.4, 18.62, 19.36, 20.6, 22.32, 23.74,
  25.1, 26.24, 27.44, 28.56, 29.54]`. 150ms initial lead 포함 split+merge는
  `31.272336s`; lead 제거 후 원본 대비 peak/RMS=`-inf dB`로 sample-identical 확인.
- 원격 문서 lint 및 `backend ./gradlew compileJava`: PASS
- 원격 solo outro Yura 합성 smoke: PASS — 문구 `여러분은 어떻게 생각하세요? 댓글로 알려주세요.`,
  raw duration `2.883855s`, loudness `input_i=-16.23 LUFS` / `input_tp=-1.50 dBTP`, initial
  silence `0.095s`, natural internal pauses, raw tail silence `0.131s`. renderer는 마지막 댓글
  발화 종료 뒤 기존 화면을 `0.25s` 유지하고, raw lead는 PCM `-45 dBFS` threshold/3-frame debounce로
  측정한다. raw lead가 95ms인 경우 부족한 약 `0.055s`만 prepend해 text→first-syllable lead를 150ms로
  맞춘 뒤 post-tail `0.50s`를 추가한다.
- 문서 검사: `python3 scripts/lint_docs.py` → PASS
- 운영 배포/실제 전체 렌더: PASS — backend image rebuild, ai_worker pycache 제거/restart 후 Again Spring job `#454`가 `READY`가 됐다. 최종 MP4는 `1080x1920`, CFR 30fps, video `55.766667s`/1673 frames, audio `55.770000s`(차이 `3.333ms`)다. 첫 text→speech `0.149592s`, outro text→speech `0.150159s`, integrated `-16.7 LUFS`, true peak `-1.5 dBFS`를 실측했다. 1→2→3줄 누적과 다음 줄 reset, 새 solo closing 화면도 추출 프레임으로 확인했다. `autoPublish=false`라 게시되지는 않았다.

## 4. 수동 테스트 방법

1. ai_worker 컨테이너에서 Again Spring 사연(댓글 1개 이상, `paired` 각각)을 렌더링한다.
2. 첫 내레이션은 텍스트가 약 150ms 먼저, 본문은 한 줄씩 세 줄까지 누적되는지 확인한다.
3. 세 번째 줄 뒤 다음 줄에서 이전 세 줄이 사라지는지 확인한다.
4. 마지막 댓글 발화가 끝난 뒤 기존 화면이 250ms 유지되고, 그 뒤 클로징 텍스트가 나타난 뒤 약 150ms 후 실제 첫 음절이 시작하며, 발화 종료 후 500ms가 남는지 확인한다.
5. `ffprobe`로 최종 MP4 audio/video duration이 오디오 타임라인을 초과하지 않는지 확인한다.

## 5. 추천 commit message

`fix(renderer): align sequential text to narration and cap final timeline`

## 6. Doc-Sync

`docs/_index.md` 트리거 맵 기준 갱신:

- `docs/20-containers/config.md`
- `docs/30-components/pipeline.md`
- `docs/50-api/rest-spec.md`
- `docs/60-runtime/pipeline-runtime.md`

`README.md`: 설치/구조/링크 변경이 없어 갱신하지 않음.

## 남은 위험

- #449 narrator 정렬·무손상 재결합 real smoke와 #454 전체 운영 렌더의 audio/video duration cap이 모두 통과했다.
- static mux의 2-frame isolated smoke는 tpad/CFR 보정 전 실패했으나, 보정 후 원격 actual renderer smoke에서 video/audio 차이 1 frame 이내와 extra tail/early video end 없음을 확인했다.
- ASR 정렬 confidence가 0.55 미만이거나 모델 로드에 실패하면 안전하게 장면별 TTS로 폴백한다. 해당 폴백의 실제 음성 품질은 별도 청감 검증이 필요하다.
- #449 smoke에서 확인된 `/.cache/huggingface/xet` 권한 실패는 설정 단계에서 writable cache root와 `HF_HUB_DISABLE_XET=1`을 적용해 보완했다. remote sync 후 해당 환경에서 HF cache download를 다시 확인한다.
- SceneDirector의 선택적 LLM 호출이 운영 렌더 중 504를 반환했지만 rule-based 폴백으로 영상은 정상 완성됐다. LLM gateway 지연은 별도 운영 개선 대상이다.
