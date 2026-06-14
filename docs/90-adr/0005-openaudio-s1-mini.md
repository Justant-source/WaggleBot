# ADR-0005: TTS 모델 OpenAudio S1-mini 업그레이드 + 참조 음성 reference_id 구조

> **status:** accepted
> **date:** 2026-06-12
> **related:** env/docker-compose.yml, worker/ai_worker/tts/fish_client.py, config/settings.py, config/voices.json, worker/tools/prepare_voice.py, docs/services.md, docs/pipeline.md

## 컨텍스트

Fish Speech 1.5.1 기반 TTS는 두 가지 한계에 막혀 있었다.

1. **자연성 한계.** 1.5는 감정 표현(인라인 마커)을 지원하지 않아 모든 씬이 동일 톤으로
   읽혔다. 짧은 텍스트·참조 부재 시 중국어로 회귀하는 문제를 막기 위해 코드 곳곳에
   방어 해킹이 누적됐다(temperature 0.5 하향, 짧은텍스트 한국어 패딩, 0.35초/자 검증).
2. **참조 음성 부재.** `assets/voices/`가 비어 있어 8개 프리셋 전부 `references=[]`로
   폴백 → 음색이 항상 기본값으로 고정되고 언어가 불안정했다. 평면 파일 + base64 업로드
   방식은 멀티 샘플·서버 캐시를 활용하지 못했다.

## 결정

1. **모델: Fish Speech 1.5.1 → OpenAudio S1-mini** (동일 fishaudio 팀 후속작).
   - 한국어 공식 지원(13개 언어), ~50종 인라인 감정 마커 `(sad)(whispering)(joyful)…`.
   - ~0.5B llama + DAC decoder, **실측 ~5~6GB VRAM(bfloat16)** → VIDEO 12.7GB와 공존 시
     ~18GB < MAX_COEXIST 20GB 무위반. (`--half` 미지정 시 기본 bf16 — fp32 아님.)
   - 라이선스 CC-BY-NC-SA-4.0 — 기존 1.5와 동일 등급(비상업), 법적 리스크 변화 없음.

2. **서버 이미지: 공식 S1 커밋에서 직접 빌드** (`wagglebot/fish-speech-s1:cuda`).
   - ⚠ **사전빌드 fishaudio/fish-speech 태그 중 s1-mini 호환 이미지가 없다** (검증으로 확인):
     - `server-cuda`(rolling, S2): FishTokenizer가 HF `AutoTokenizer`라 s1-mini의
       tiktoken(`config.json: model_type=dual_ar`)을 못 읽음 → tokenizer=None →
       warm-up `'NoneType'.encode` 크래시 루프.
     - `v1.5.1`: firefly decoder/8 codebook → modded_dac/10 codebook(s1-mini) 미지원.
     - OpenAudio S1은 **별도 버전 태그 없이 main 브랜치로만 릴리스** (v1.5.1↔v2.0.0-beta(S2) 사이).
   - 따라서 tiktoken + modded_dac을 둘 다 가진 S2 직전 S1 tip 커밋
     **`d3df50503b36`(2026-01-08)**에서 `docker/Dockerfile`(server/cuda)로 빌드.
     그 커밋 server 타겟의 기본 ARG가 이미 `openaudio-s1-mini`/`modded_dac_vq` → s1-mini 정본.
     재빌드: **`scripts/build_fish_speech_s1.sh`**.
   - env 기반 엔트리포인트(`/app/start_server.sh`가 `${LLAMA_CHECKPOINT_PATH}` 셸 확장).
   - 컨테이너가 **UID 1000으로 실행**되며 `validate_env`가 `/app/references` 쓰기 권한을
     요구 → `assets/voices`를 **UID 1000 소유로 chown** 필수 (아니면 서버 기동 실패).
   - healthcheck: `curl`로 포트 리스닝 검사(라우트 독립). start_period 180s.
     warm-up은 의존성 베이킹되어 ~17초.

3. **참조 음성: 폴더 기반 `reference_id` 구조.**
   - `assets/voices/<key>/NN.wav + NN.lab` (마운트 → 서버 `/app/references/<key>/`).
   - 클라이언트는 `reference_id: <key>` + `use_memory_cache: "on"` 전송 → base64 업로드 제거,
     서버가 인코딩을 메모리 캐시. 폴더 부재 시 레거시 평면파일 base64, 그것도 없으면
     `references=[]` + 경고.
   - 등록은 `worker/tools/prepare_voice.py`(faster-whisper 자동 전사)로 수행.

4. **생성 파라미터 정상화.** temperature 0.5→0.8, repetition_penalty 1.3→1.1, top_p 0.8 추가,
   `language` 필드 제거(1.5 잔재, S1에서 무시됨), `normalize: false`(자체 한국어 정규화 사용).
   감정 마커는 `tts_emotion`(scene_policy.json) → `TTS_EMOTION_MARKERS`로 매핑해 주입.

## 근거

- S1-mini는 1.5의 직접 후속으로 **동일 API 서버·동일 reference 개념**을 쓰므로 마이그레이션
  비용이 낮다. 구 클라이언트 페이로드도 신 서버와 순방향 호환(`language` 무시, base64 자동 디코드)
  → 서버를 먼저 교체해도 중간 상태가 동작한다.
- 감정 마커는 mood별 톤(감동=부드럽게, 충격=놀람 등)을 표현 가능하게 해 리텐션에 직접 기여.
- reference_id + 메모리 캐시는 매 요청 base64 업로드(수백 KB)를 제거해 지연을 줄인다.

## 롤백

1. `env/docker-compose.yml` fish-speech `image:`를 `fishaudio/fish-speech:v1.5.1`로 변경,
   `working_dir: /opt/fish-speech` + 구 `entrypoint`(api_server.py + firefly decoder + --half) 복원,
   볼륨을 `../checkpoints:/opt/fish-speech/checkpoints` + `../assets/voices:/opt/fish-speech/references`로,
   healthcheck를 구 urllib python 검사로 되돌린다.
2. 체크포인트 `checkpoints/fish-speech-1.5/`는 **삭제하지 않고 보존**되어 즉시 복귀 가능.
   빌드한 `wagglebot/fish-speech-s1:cuda` 이미지도 남겨두면 재빌드 없이 재전환 가능.
3. `config/settings.py`의 `FISH_SPEECH_TEMPERATURE=0.5`, `REPETITION_PENALTY=1.3`로 되돌리고
   `FISH_SPEECH_NORMALIZE`/`TTS_EMOTION_ENABLED`를 끄면 구 동작에 근접.

## 영향

- VRAM: 실측 ~5~6GB(bf16) — VIDEO와 공존 시 ~18GB < 20GB. 하드 제약 무변경.
- CLAUDE.md 하드 제약 무변경 (FFmpeg/ComfyUI/VRAM/Phase 5‖6 그대로). TTS 락 유지(ADR-0003).
- 신규 의존성 `faster-whisper`(prepare_voice 전용) → ai_worker 이미지 리빌드 필요.
- 빌드 산출물 `wagglebot/fish-speech-s1:cuda`(로컬, ~6.2GB)는 레지스트리 미푸시 — 다른 머신
  배포 시 `scripts/build_fish_speech_s1.sh` 재실행 필요.

## 라이브 검증 결과 (A3, 2026-06-12 실측)

- ✅ 모델 로드 `<All keys matched successfully>` (llama+decoder), tokenizer(tiktoken) 정상, warm-up 통과, healthy.
- ✅ VRAM ~5~6GB (bf16). WAV 출력 **44100Hz mono 16bit** (렌더러 concat 호환).
- ✅ JSON 수락, 새 페이로드(top_p/normalize:false/language제거) 정상, 한국어 합성 자연(초/자 0.08~0.11).
- ✅ 감정 마커 4종(none/sad/whispering/surprised) 주입·합성. 장문 185자→2세그먼트 분할·병합.
- ✅ RTF: 문장당 ~6~9초 (300자도 타임아웃 300s 내). `--compile` 미적용 — 필요 시 COMPILE=1로 가속 가능.
- ⏳ reference_id 음성 클로닝: 코드 경로 검증 완료, 실제 녹음 등록(prepare_voice) 후 가청 검증 권장.
