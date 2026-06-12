# tts-s1-upgrade

## 1. 작업 결과

한국어 TTS 자연성과 음성 복제 능력을 끌어올리기 위해 **Fish Speech 1.5.1 → OpenAudio S1-mini**(동일 fishaudio 팀 후속작)로 업그레이드하고, 녹음 음성을 떨어뜨리면 **faster-whisper 자동 전사**로 reference_id 클로닝에 등록되는 파이프라인을 구축했다.

핵심 개선 4가지:
1. **감정 표현** — mood별 톤(`(sad)`/`(whispering)`/`(joyful)` 등)을 인라인 마커로 주입. 1.5는 불가능했던 부분.
2. **음성 복제 구조** — base64 평면파일 → 폴더 기반 `reference_id`(NN.wav+NN.lab) + 서버 메모리 캐시. 멀티 샘플·저지연.
3. **한국어 정규화 대폭 강화** — 소수/콤마/범위/유월·시월/도량형 단위/전화번호 + 영문 약어 + **흔한 단어 망가뜨리던 조사 교정 버그 수정**(마을→마를, 사과→사와 회귀 제거).
4. **합성 품질** — loudnorm 음량 일관성, 장문 자동 분할, WAV 헤더 기반 길이 검증.

**검증 완료(오프라인 + 라이브 A3):** 정규화 단위 테스트 **29/29 통과**, 전 모듈 컴파일·import OK, prepare_voice e2e 동작. **라이브: S1-mini 서버 healthy, 한국어 합성 4/4·감정 마커 4종·장문 분할 전부 통과**(아래 §3).

> 🔧 **배포 중 발견 + 해결:** 사전빌드 fishaudio/fish-speech 태그 중 **s1-mini 호환 이미지가 없었다** — `server-cuda`(rolling)는 S2용 HF AutoTokenizer라 s1-mini의 tiktoken(model_type=dual_ar)을 못 읽어 warm-up 크래시, `v1.5.1`은 modded_dac 미지원, OpenAudio S1은 별도 태그 없이 main에만 릴리스. 사용자 승인 하에 **공식 S1 커밋 `d3df50`(2026-01-08)에서 server/cuda 이미지를 직접 빌드**(`wagglebot/fish-speech-s1:cuda`)해 해결. 그 커밋 server 타겟의 기본 ARG가 이미 `openaudio-s1-mini`라 정본 확인. 재빌드: `scripts/build_fish_speech_s1.sh`.

## 2. 수정 내용

### 모델·서버 (Phase A)
- **`scripts/download_openaudio_s1.sh`** (신규): gated HF 인증 점검 + `checkpoints/openaudio-s1-mini/` 다운로드 + 검증. `fish-speech-1.5/`는 롤백용 보존.
- **`scripts/build_fish_speech_s1.sh`** (신규): S1 커밋 d3df50 소스 다운로드 → server/cuda 이미지 빌드. 사전빌드 태그 비호환 우회.
- **`env/docker-compose.yml`** fish-speech 블록 교체:
  - 이미지 `wagglebot/fish-speech-s1:cuda` (로컬 빌드)
  - env 오버라이드 `LLAMA_CHECKPOINT_PATH`/`DECODER_CHECKPOINT_PATH`
  - 서브디렉토리 마운트(ComfyUI 모델 미노출), `assets/voices:/app/references`
  - `curl` healthcheck(라우트 독립), start_period 180s
  - **assets/voices를 UID 1000 소유로 chown** (이미지가 UID 1000 실행 + validate_env 쓰기 권한 검사)

### 설정 (Phase B)
- **`config/settings.py`**: temp 0.5→0.8, rep 1.3→1.1, top_p/normalize/chunk_length/use_memory_cache/seed 추가, TTS_SPEED/LOUDNORM/MAX_CHARS/EMOTION/LAUGH 게이트, `TTS_EMOTION_MARKERS`(신규, EMOTION_TAGS와 별개 축), WHISPER_* 설정, `_load_voice_presets` v2 재작성.
- **`config/voices.json`** v2: `{key, label, ref_dir, file, params}`. `file`은 `<key>/01.wav`로 유지 → Java VoiceCatalogService sampleUrl·프론트 무수정.

### 클라이언트 (Phase C)
- **`worker/ai_worker/tts/fish_client.py`** 재작성: `_resolve_references`(reference_id 우선 체인), 페이로드 정상화(`language` 제거·top_p/normalize 추가·per-voice params 머지), 감정 마커 주입(품질검증은 마커 제외 글자수 기준), 장문 분할+concat, `_wav_duration`(헤더 파싱, SR 독립), 후처리 `loudnorm→44100 강제`(렌더러 concat 호환), 웜업 간소화. TTS 락(ADR-0003) 유지.
- **`worker/ai_worker/tts/normalizer.py`**:
  - 슬랭 로더 **merge 버그 수정**(JSON이 내장 사전 교체 → 병합). `assets/`는 gitignore라
    핵심 약어(CCTV/SNS/AI 등)를 **`_SLANG_MAP_BUILTIN`(코드)에 내장** — assets/slang_map.json은 선택적 오버라이드
  - 조사 교정을 **슬랭 경계로 한정**(`apply_ko_slang`) — 전역 fix_particles의 마을/사과/가을 망가뜨림 제거
  - 숫자 확장: 소수(3.5→삼 점 오)·콤마·범위(3~4명)·유월/시월·단위(km/GB)·전화번호
  - 영문 약어 별도 패스(조사교정 후, 단어경계) — AI→에이아이가 '에이아가'로 망가지던 회귀 차단
  - ㅋㅋ→`(laughing)` 게이트(기본 off)
- **`worker/ai_worker/tts/number_reader.py`**: `read_digits`(자릿수 읽기, 0=공) 추가.

### 감정 배선 (Phase C3)
- `pipeline/content_processor.py`, `renderer/layout.py`(6개 sentence dict), `renderer/_tts.py`, `dashboard_worker/handlers.py`에 `emotion=scene.tts_emotion` 전달.

### 음성 등록 (Phase D)
- **`worker/tools/prepare_voice.py`** + `__init__.py`(신규): ffmpeg 정제(mono/44.1k/loudnorm/트림) → silencedetect 8~15초 세그먼트 → faster-whisper(ko, CPU int8) 전사 → `assets/voices/<key>/NN.wav+NN.lab` + voices.json 갱신. 재등록 시 fish-speech 재시작 안내.
- **`worker/requirements.txt`**: `faster-whisper>=1.1.0` (이미지 리빌드 필요).

### 테스트·문서 (Phase E)
- **`worker/test/test_tts_normalizer.py`**(신규, 29 케이스 오프라인 통과), **`test_fish_speech.py`** 재작성(URL 버그 수정, synthesize 통합 경로, 감정/장문/음성별).
- ADR-0005 신규 + DOC-MAP 등록, services/config/pipeline/architecture/implementation-status 갱신, env/.env 포트(8082) 수정.

## 3. 테스트 결과물 위치

- **정규화 단위 테스트:** `worker/test/test_tts_normalizer.py` → **29/29 통과** (컨테이너 내 실행 확인)
- **라이브 통합 테스트:** `worker/test/test_fish_speech.py` → 출력 `worker/test/test_tts_output/`
  (basic_1~4.wav, emotion_{none,sad,whispering,surprised}.wav, long_split.wav + summary.json + test_log.txt)
- **prepare_voice e2e:** `--transcript` 모드로 정제·세그먼트·등록·voices.json 갱신 동작 확인(잔여물 정리 완료).

### A3 라이브 검증 실측 (2026-06-12, S1-mini 서버 healthy)
- ✅ 모델 로드 `<All keys matched successfully>`, tokenizer(tiktoken) 정상, **warm-up 통과**(~17s), healthy
- ✅ VRAM **~5~6GB(bf16)** — VIDEO 12.7GB와 공존 ~18GB < 20GB 하드 제약 OK
- ✅ WAV 출력 **44100Hz mono 16bit** (렌더러 concat 호환)
- ✅ 한국어 합성 **4/4**, 초/자 0.08~0.11(정상 범위 — 중국어 회귀·잘림 없음)
- ✅ 감정 마커 4종 주입·합성, 장문 **185자→2세그먼트 분할·병합**
- ✅ RTF 문장당 ~6~9초(타임아웃 300s 내), 새 페이로드(top_p/normalize:false/language제거) 정상
- ⏳ reference_id 클로닝: 코드 검증 완료, 실제 녹음 등록(prepare_voice) 후 가청 검증 권장

## 4. 수동 테스트 방법

> 모델 다운로드·서버 교체·A3 검증·ai_worker 리빌드는 **이미 완료**됨. 아래는 재현/추가 검증용.

**현재 상태 확인:**
```bash
docker compose -f env/docker-compose.yml ps          # fish-speech → healthy
docker compose -f env/docker-compose.yml exec ai_worker python test/test_fish_speech.py
# → test_tts_output/ 의 basic_*.wav(자연성)·emotion_*.wav(마커별 톤 차이) 청취
```

**핵심 다음 단계 — 음성 복제 (사용자 목소리 등록):**
```bash
# 녹음(10~30초, 깨끗한 한국어)을 assets/voices_raw/ 에 두고:
docker compose -f env/docker-compose.yml exec ai_worker \
  python -m tools.prepare_voice --input assets/voices_raw/내목소리.wav --key default --label "기본" --preview
docker compose -f env/docker-compose.yml restart fish-speech   # reference_id 캐시 갱신
# 이후 합성은 default 음성이 등록된 목소리로 클로닝됨
```

**정규화 단위 테스트 (오프라인):**
```bash
docker compose -f env/docker-compose.yml exec ai_worker python test/test_tts_normalizer.py   # 29/29
```

**서버 재빌드 (다른 머신 배포·이미지 손실 시):**
```bash
bash scripts/download_openaudio_s1.sh    # HF_TOKEN 필요 (gated)
bash scripts/build_fish_speech_s1.sh     # S1 커밋에서 이미지 빌드
```

## 5. 추천 commit message

```
feat: TTS OpenAudio S1-mini 업그레이드 + reference_id 음성 복제·감정 마커 (ADR-0005)

- 모델: Fish Speech 1.5.1 → OpenAudio S1-mini (한국어 감정 마커, bf16 ~5-6GB)
- 서버: 사전빌드 태그 비호환 → S1 커밋 d3df50에서 직접 빌드(wagglebot/fish-speech-s1:cuda),
        build_fish_speech_s1.sh, UID 1000 references chown
- 음성: 폴더 reference_id(NN.wav+NN.lab) + memory cache, prepare_voice 자동 전사(faster-whisper)
- 정규화: 조사 교정 슬랭 경계 한정(마을→마를 회귀 수정), 숫자/약어 확장
- 클라이언트: 감정 마커 주입, 장문 분할, WAV 헤더 검증, loudnorm 후처리
- 감정 배선 4곳, voices.json v2, 정규화 테스트 29/29
- A3 라이브 검증 통과(합성 4/4·감정 4종·장문 분할), ai_worker 리빌드 활성화

fish-speech-1.5 롤백 자산 보존.
```

## 6. DOC-MAP 기준 갱신한 문서 목록

- `docs/adr/0005-openaudio-s1-mini.md` (신규) — 모델 결정·이미지 호환성 발견·빌드·롤백·A3 실측 결과
- `docs/DOC-MAP.md` — ADR 표에 0005 등록
- `docs/services.md` — fish-speech 서비스 블록(커스텀 빌드 이미지/볼륨/healthcheck/env)
- `docs/config.md` — TTS 설정 표·voices.json v2·감정 마커·Whisper
- `docs/pipeline.md` — Phase 5 TTS(reference_id·감정·분할·후처리·검증)
- `docs/architecture.md` — VRAM 배분(S1-mini), TTS 스택, 다이어그램 라벨
- `docs/implementation-status.md` — S1-mini 업그레이드 배치 항목
- `env/.env` — FISH_SPEECH_URL 호스트 포트(8082) + HF_TOKEN 추가

**신규 스크립트(문서 아님):** `scripts/download_openaudio_s1.sh`, `scripts/build_fish_speech_s1.sh`

(CLAUDE.md 하드 제약 무변경 → 미수정)
