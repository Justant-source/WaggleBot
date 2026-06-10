# TTS 프리뷰 버그 수정 결과

## 1. 작업 결과

`_handle_tts_preview` 함수에서 존재하지 않는 `FishSpeechClient` 클래스를 참조하던 ImportError 버그를 수정했습니다. 실제 `synthesize` async 함수로 교체하고, 출력 포맷 수정 및 `scope` 파라미터 지원을 추가했습니다.

## 2. 수정 내용

**파일:** `worker/dashboard_worker/handlers.py` (65~111행)

| 항목 | 변경 전 | 변경 후 |
|------|---------|---------|
| import | `from ai_worker.tts.fish_client import FishSpeechClient` | `import asyncio` + `from ai_worker.tts.fish_client import synthesize` |
| 클라이언트 사용 | `FishSpeechClient().synthesize(text, str(output_path), voice=voice)` | `asyncio.run(synthesize(text, voice_key=voice_key, output_path=output_path))` |
| 출력 확장자 | `.mp3` (하드코딩) | `.{TTS_OUTPUT_FORMAT}` (설정값 `"wav"` 반영) |
| 파라미터명 | `voice=` (잘못된 키) | `voice_key=` (synthesize 시그니처 일치) |
| `scope` 지원 | 없음 | `"full"` — hook+전체body+closer, `"preview"`(기본) — hook+body[:3] |
| output_path 타입 | `str(output_path)` | `Path` 객체 직접 전달 (synthesize가 Path 반환) |
| 반환값 | `{"preview_path": str(output_path)}` | `{"preview_path": str(audio_path)}` (synthesize 반환 Path 사용) |

## 3. 테스트 결과물 저장 위치

TTS 프리뷰 오디오 파일: `assets/media/tmp/preview_{post_id}.wav`

## 4. 수동 테스트 방법

1. DB에 APPROVED 상태 Post와 ScriptData가 있는 Content 확인
2. dashboard_worker 컨테이너 내에서:
   ```python
   from dashboard_worker.handlers import _handle_tts_preview
   from db.models import Job, JobType
   job = Job(post_id=<post_id>, job_type=JobType.TTS_PREVIEW, payload={})
   result = _handle_tts_preview(job)
   print(result)  # {"preview_path": ".../preview_<id>.wav"}
   ```
3. 또는 프론트엔드 편집기에서 TTS 미리듣기 버튼 클릭 후 오디오 재생 확인
4. scope 테스트: `payload={"scope": "full"}` 전달 시 전체 대본 TTS 생성 확인

## 5. 추천 commit message

```
fix: TTS 프리뷰 FishSpeechClient ImportError 수정

- FishSpeechClient(미존재 클래스) → synthesize() async 함수로 교체
- asyncio.run()으로 sync 컨텍스트에서 안전 호출
- 출력 포맷 .mp3 하드코딩 → TTS_OUTPUT_FORMAT(wav) 적용
- voice= → voice_key= (synthesize 시그니처 일치)
- scope="full" 지원: hook+전체body+closer TTS 생성
```
