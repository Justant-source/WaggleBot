# multi-voice: 다화자 TTS 음성 배정

## 1. 작업 결과

19개 신규 음성을 등록하고, 사연자 연령/성별 추정 → 내레이터 자동 배정, 등장인물 직접 발화 → 별도 character voice 배정이 동작하도록 파이프라인 전체를 연결했다.

## 2. 수정 내용

| 파일 | 변경 내용 |
|------|----------|
| `config/voices.json` | v2→v3 업그레이드. 19개 신규 음성 추가 (기존5 + 신규19 = 24개). 각 항목에 `gender`, `age_range` 필드 추가. |
| `config/settings.py` | `_load_voice_presets()`에서 `gender`, `age_range` 필드 포함하여 로드. |
| `worker/ai_worker/script/voice_assigner.py` | **신규 파일.** `pick_voice(gender, age, exclude)` — VOICE_PRESETS 메타데이터 기반 성별 우선 + 연령 근접 선택. |
| `worker/ai_worker/script/chunker.py` | LLM 출력 스키마 확장 (extended 모드): `narrator_gender`, `narrator_age` 추가. body 항목에 `speaker`/`character_label`/`character_gender`/`character_age` 필드 추가. 화자 태깅 규칙 주입. |
| `worker/ai_worker/scene/director.py` | `SceneDirector.__init__`에 `narrator_voice`, `_character_voices` 추가. body 루프에서 character 항목 → `_assign_character_voice()` 호출. `_assign_character_voice()` 메서드 신규 추가. |
| `worker/ai_worker/pipeline/content_processor.py` | chunker 출력에서 `narrator_gender`/`narrator_age` 추출 → `pick_voice()` 호출 → `narrator_voice` 결정 → `SceneDirector`에 전달. |

## 3. 테스트 결과물 위치

없음 (파이프라인 통합 테스트는 수동 검증 필요)

## 4. 수동 테스트 방법

### 4-1. voices.json 파일 구조 준비 (필수 선행 작업)

각 신규 음성에 대해 `assets/voices/<key>/01.wav` + `01.lab` 파일을 생성해야 fish-speech reference_id 클로닝이 동작한다.

```bash
# 예시: anna_kim 음성 등록
mkdir -p assets/voices/anna_kim
# assets/media/voices/voice_preview_anna kim 파일을 복사 후 이름 변경
cp "assets/media/voices/voice_preview_anna kim" assets/voices/anna_kim/01.wav
# 01.lab 파일에 해당 음성의 전사 텍스트 작성 (내용은 실제 녹음 내용)
echo "안녕하세요. 반갑습니다." > assets/voices/anna_kim/01.lab
```

모든 19개 음성에 동일하게 적용 (key 목록: `anna_kim blondie callie christian deep_lax han hope ivanna krishna lucy manbo manu miguel min_jun norah tara theo yohan_koo yura`).

### 4-2. 음성 선택 로직 단독 테스트

```python
from ai_worker.script.voice_assigner import pick_voice
print(pick_voice("female", "20s"))       # → anna_kim (23-27)
print(pick_voice("male",   "40s"))       # → default/christian/manbo (43-47 중 하나)
print(pick_voice("female", "30s", exclude={"han"}))  # han 제외 후 최근접
```

### 4-3. 파이프라인 전체 테스트

```bash
# ai_worker 컨테이너에서 실행
docker compose -f env/docker-compose.yml exec ai_worker python -m pytest worker/test/ -k "e2e" -s
# 또는 수신함에서 게시글을 APPROVED 상태로 전환 후 처리 로그 확인
docker compose -f env/docker-compose.yml logs --tail 100 ai_worker | grep -E "narrator_voice|character|voice="
```

기대 로그:
```
[content_processor] narrator_voice=yura (gender=female, age=20s)
[director] character '남자친구' → voice=krishna
```

## 5. 추천 commit message

```
feat: 19개 신규 음성 등록 + 다화자 TTS 자동 배정

- voices.json v3: gender/age_range 메타데이터 + 19개 음성 추가 (총 24개)
- voice_assigner.py: pick_voice(gender, age, exclude) 성별우선·연령근접 선택
- chunker.py: narrator_gender/age + speaker/character 화자 태깅 스키마 추가
- director.py: narrator_voice 파라미터 + character_label별 voice 캐시·배정
- content_processor.py: chunker 출력 → narrator_voice → SceneDirector 연결
```

## 6. 갱신한 문서 목록

없음 (docs/pipeline.md의 Phase 5 TTS 섹션에 다화자 배정 흐름 추가 권장)
