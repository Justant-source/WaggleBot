# ADR-0006: TTS를 외부 Local-TTS 제공자로 전환 (Fish Speech 폐기)

> **status:** accepted (코드·문서 완료, 운영 미적용 — 2026-11-27)
> **date:** 2026-11-27
> **supersedes:** [ADR-0005](0005-openaudio-s1-mini.md)
> **related:** env/docker-compose.yml, config/settings.py, worker/ai_worker/tts/synth.py, worker/ai_worker/tts/local_tts_client.py, worker/ai_worker/core/main.py, worker/ai_worker/core/processor.py, docs/shared/20-containers.md, docs/worker/60-runtime.md

## 컨텍스트

Fish Speech(S1-mini → S2-pro)는 WaggleBot compose 안의 GPU 컨테이너였다. 이 구조는 다음 비용을 낳았다.

- **VRAM 핸드오프:** S2-pro는 유휴에도 ~20GB 상주 → Phase 7(ComfyUI) 진입 전 `container_control.py`가 `docker.sock`으로 컨테이너를 stop/start 해야 했다(`group_add: "989"`, `/var/run/docker.sock` 마운트).
- **게이트·임대:** Flight-Brain `atomic_tts` GPU 데몬이 Fish 수명주기를 관리(유휴 10분·X-Plane 시 정지)해, WaggleBot이 `fish_gate.py`로 문의·대기·임대·재큐 로직을 따로 유지했다.
- **중복 구현:** 정규화(`normalizer.py`·`number_reader.py`)가 Flight-Brain에서 복사 후 분기했다(소수점 `점`/`쩜`). 같은 TTS를 두 앱이 각자 운영했다.

Flight-Brain과 WaggleBot이 함께 쓰는 별도 저장소 서비스 **Local-TTS**(`/home/justant/Data/Local-TTS`, Supertonic 엔진, job 큐·서버 정규화·청크·loudnorm·발음 프로필)가 준비됐다.

## 결정

1. **Fish Speech 완전 폐기.** `fish-speech` 컨테이너, `docker.sock`·`group_add`, `FISH_*`/`ATOMIC_TTS_FISH_GATE_URL` 설정, `fish_client.py`·`fish_gate.py`·`container_control.py`·`quality.py`·웜업 센티널·`prepare_voice.py`·참조 음성 합성 사용을 삭제한다. ADR-0005는 폐기로 표시한다.
2. **제공자 모델.** WaggleBot은 합성 코드·게이트·임대·컨테이너 제어를 갖지 않고 Local-TTS에 `POST /v1/jobs`만 요청한다.
   - 주소 `http://local-tts:8500`, 외부 Docker 네트워크 `local_tts_net`(`external: true`, **사전 생성 필수**)에 `ai_worker`·`dashboard_worker`만 합류.
   - client id `wagglebot`(= `X-Client-Id` = 프로필 네임스페이스), 프로필 `wagglebot/shorts-ko` v1.
   - 요청 옵션: `lang=ko`, `speed=TTS_SPEED(1.1)`, `chunk max_chars 120`, `loudnorm i=-16 tp=-1.5`, `output wav`. 속도는 서버 한 곳에서만 적용(로컬 atempo 없음, 이중 적용 금지).
3. **앱 간 import 금지 유지.** 클라이언트는 Local-TTS 저장소의 `client/local_tts_client.py` **복사본**을 `worker/ai_worker/tts/local_tts_client.py`에 둔다(원본 직접 수정 금지).
4. **서버 장애는 FAILED가 아니다.** 연결 실패·타임아웃·429/503·큐 포화·대기 초과는 `TTSUnavailable`(일시 장애). 집기 전 `/readyz` 확인이 실패하면 APPROVED 폴링을 보류하고, 처리 중이면 `PROCESSING → APPROVED`로 되돌리며 `retry_count`를 유지한다. 서버 대기 상한의 SSOT는 `TTS_SERVER_MAX_WAIT_SEC`(3600s) 하나다. (설계 초안의 "지수 백오프 후 FAILED"가 아니라 재큐를 채택 — Local-TTS가 내려가도 승인된 글을 잃지 않는다.)
5. **폐기 기능:** 감정 마커, `ㅋㅋ` 웃음 마커, 웜업, 참조 음성, 초/자 품질 재시도, 로컬 장문 분할. 디스크 TTS 캐시 버전은 `pp_v7`로 올려 구 Fish WAV 재사용을 막는다.
6. **렌더 타이밍 ASR 정렬(`alignment.py`, faster-whisper)은 이번 단계에서 유지.** 응답 `chunks[]` 타이밍 기반 전환은 후속 과제다.

## 근거

- VRAM 핸드오프·게이트·임대·`docker.sock` 마운트는 모두 "TTS가 같은 GPU의 대형 상주 컨테이너"라는 전제에서 나왔다. 제공자를 분리하면 전제가 사라져 합성 클라이언트·게이트·컨테이너 제어 코드와 관련 테스트·1회성 스크립트(변경 집계상 약 6.5천 줄 삭제)와 `docker.sock` 접근 권한이 제거된다.
- 서버가 정규화·청크·loudnorm·속도를 한 번만 수행하므로 두 앱의 TTS 규칙이 갈라지지 않는다([ADR-0008](0008-tts-normalization-standard.md)).
- 재큐 정책은 기존 Fish 차단 재큐(retry_count 유지)와 같은 의미를 유지하되 대기 루프·게이트 상태를 없앤다.

## 영향

- **VRAM 하드 제약:** WaggleBot 소유 로컬 GPU 예산에서 `TTS ~5GB` 항목을 삭제한다. 로컬 GPU 모델은 VIDEO(~12.7GB)만 남는다. Local-TTS(Supertonic)의 VRAM은 별도 저장소가 관리한다. `docs/shared/70-policy.md`의 VRAM 행이 이 ADR을 참조한다. (루트 `AGENTS.md` 하드 제약 요약의 "TTS(~5GB)+VIDEO" 문구와 `managed_inference(ModelType.TTS, "fish-speech")` 예시는 이 변경과 맞지 않으므로 별도 갱신이 필요하다. 충돌 시 `docs/shared/70-policy.md`가 우선한다.)
- **포트·네트워크:** `8082:8080` 제거, `local_tts_net` 신규. 네트워크가 없으면 두 워커 컨테이너 기동이 실패한다.
- **환경변수:** `TTS_SERVER_URL/TOKEN/TIMEOUT_SEC/RETRIES/MAX_WAIT_SEC`, `TTS_PROFILE`, `TTS_CLIENT_ID`, `TTS_SPEED` 신규. `FISH_*`·`TTS_EMOTION_*` 등 삭제.
- **상태 전이:** `PROCESSING → APPROVED` 재큐 사유에 TTS 서버 불가가 추가된다.
- **운영 미적용 항목:** 컨테이너 재생성, 마이그레이션 적용, APPROVED 재큐, 프로필 활성화, Supertonic 청취 비교는 아직 하지 않았다.

## 금지사항

- WaggleBot에 합성 모델·GPU 게이트·컨테이너 제어(`docker.sock`)를 다시 도입하지 말 것.
- 서버 장애를 post FAILED로 처리하지 말 것(`TTSUnavailable` → 재큐).
- 로컬 atempo 등으로 속도를 이중 적용하지 말 것(`TTS_SPEED`는 서버 옵션으로만).
- `local_tts_client.py` 사본을 앱 안에서 임의 수정하지 말 것(원본에서 갱신).
