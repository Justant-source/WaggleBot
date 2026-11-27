# ai_worker/tts — TTS 모듈

텍스트를 음성으로 바꾸는 모듈. 합성은 **Local-TTS 서버**(`POST /v1/jobs`)에 요청만 하며,
WaggleBot은 합성 모델·GPU 게이트·컨테이너 제어를 갖지 않는다(제공자 모델).

## 파일 구조

```
ai_worker/tts/
├── __init__.py          # 공개 API re-export
├── synth.py             # synthesize / wait_for_tts_server / TTSUnavailable (A1)
├── local_tts_client.py  # Local-TTS 클라이언트 사본(원본: Local-TTS/client, 직접 수정 금지)
├── voice_resolver.py    # 보이스 키·post_id → 프리셋 M1~M5/F1~F5
├── prenorm.py           # 앱 고유 전처리(화자 접두어·URL·해시태그 등)
├── normalizer.py, number_reader.py  # 레거시 로컬 정규화(서버 정규화·프로필로 이관 중)
├── alignment.py         # 렌더 타이밍용 ASR 정렬(유지)
└── settings.yaml
```

## 공개 API

```python
from ai_worker.tts import synthesize, wait_for_tts_server, TTSUnavailable
path = await synthesize(text, scene_type="image_text", voice_key=None,
                        output_path=None, post_id=123)   # emotion은 호환용(무시)
ok = await wait_for_tts_server(timeout_sec=None)          # /readyz 폴링
```

| 항목 | 동작 |
|------|------|
| 입력 | `prenormalize(text)` 후 읽을 글자가 없으면 `ValueError` |
| 보이스 | `resolve_voice(voice_key, post_id)` — 항상 `M1..F5`, post_id 시드 결정적 |
| 요청 | `options`: `voice`, `lang=ko`, `speed=TTS_SPEED`, `normalize.profile=TTS_PROFILE`, `chunk{max_chars,120}`, `postprocess.loudnorm(-16)`, `output.format=wav` |
| request_id | `wb-<post_id>-<scene_type>-<uuid8>` → `options.request_id` |
| 재시도 | 클라이언트가 연결 오류·타임아웃·429/503(+Retry-After)을 `TTS_SERVER_RETRIES`회 재시도 |
| 예외 | 서버 불가·타임아웃·큐 포화·job 대기 초과 → `TTSUnavailable`(일시 장애, 재큐 대상). 요청 거부·job 영구 실패 → `TTSError`(RuntimeError) |
| 동기/비동기 | 동기 httpx 클라이언트를 `asyncio.to_thread`로 감싼다 |

## 설정 (config/settings.py, 환경변수는 settings.py에서만 읽음)

`TTS_SERVER_URL`(기본 `http://local-tts:8500`), `TTS_SERVER_TOKEN`, `TTS_SERVER_TIMEOUT_SEC`,
`TTS_SERVER_RETRIES`, `TTS_SERVER_MAX_WAIT_SEC`, `TTS_PROFILE`(`wagglebot/shorts-ko`),
`TTS_CLIENT_ID`(`wagglebot` = `X-Client-Id` = 프로필 네임스페이스), `TTS_SPEED`(서버 speed, 로컬 atempo 없음).

## 폐기된 것

Fish Speech 클라이언트·게이트·웜업·참조 음성·감정 마커·`ㅋㅋ` 웃음 마커·품질(초당 글자) 재시도·로컬 150자 분할.
