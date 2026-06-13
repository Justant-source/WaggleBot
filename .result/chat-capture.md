# chat-capture — P5 카카오톡 대화 버블 씬 신규 SceneType

## 1. 작업 결과

LLM이 본문에서 대화(카카오톡·문자 등)를 추출하면 **카카오톡 UI 스타일 버블 씬**으로 자동 렌더링하는 `chat` SceneType을 추가했다.

- `is_mine=true` → 우측 노란 버블 `#FFE100`
- `is_mine=false` → 좌측 회색 버블 `#F2F2F2` + 아바타(해시 색상 원 + sender 첫 글자) + 발신자 이름
- 연속 메시지 간 10px, 발신자 전환 시 28px group_gap
- 4메시지/씬, 씬당 3.5초 무음 체류(TTS 없음)
- 오버플로우 보호: canvas 하단 80px 이내면 렌더링 중단

컨테이너 테스트 3개 PNG 전부 통과 — 버블 좌우 배치·아바타·발신자 이름·제목 블록 정상 확인.

## 2. 수정 내용

| 파일 | 변경 내용 |
|------|----------|
| `config/layout.json` | `scenes.chat` 블록 추가 (dwell_sec·side_pad·bubble 색상·font_size·avatar_d 등) |
| `config/scene_policy.json` | `scene_rules.chat` 추가 (enabled·max_messages_per_scene:4·narrate:false·dwell_sec:3.5) |
| `worker/db/models.py` | `ScriptData`에 `chat_messages: list[dict]` 필드 추가, `to_json`/`from_json` 갱신 |
| `worker/ai_worker/script/chunker.py` | `extended_fields`에 `chat_messages` 스키마 추가, 섹션 5 대화 추출 지침 추가 |
| `worker/ai_worker/scene/director.py` | `SceneType`에 `"chat"` 추가, `SceneDecision`에 `dwell_sec`·`chat_messages` 필드, `direct()`에 chat 씬 생성 블록 |
| `worker/ai_worker/renderer/_frames.py` | `_render_chat_frame()` 신규 (카카오톡 버블 PIL 렌더러) |
| `worker/ai_worker/renderer/layout.py` | `_scenes_to_plan_and_sentences`에 `"chat"` 분기, Step-8 디스패치에 `chat` 케이스 |
| `worker/ai_worker/pipeline/content_processor.py` | `chat_messages` 추출 후 SceneDirector에 전달 |
| `worker/ai_worker/core/processor.py` | `llm_tts_stage`·`render_stage`·인라인 SceneDirector 경로 모두 `chat_messages` 전달 |

## 3. 테스트 결과물 위치

컨테이너 테스트 PNG 3개:
```
/tmp/wb_chat_test/chat1.png  — 남친 이별 카톡 ("우리 그만 만나자" / "갑자기 무슨 소리야?")
/tmp/wb_chat_test/chat2.png  — 시어머니 명절 음식 대화 (4메시지)
/tmp/wb_chat_test/chat3.png  — 시어머니 명절 음식 대화 (3메시지, 2번째 씬)
```

## 4. 수동 테스트 방법

```bash
# ai_worker 컨테이너에서 실행
docker compose -f env/docker-compose.yml exec ai_worker bash

python - <<'EOF'
from pathlib import Path
from ai_worker.renderer._frames import _render_chat_frame
from ai_worker.renderer.layout import _load_layout_config

layout = _load_layout_config()
font_dir = Path("/usr/share/fonts")
out = Path("/tmp/wb_chat_test")
out.mkdir(exist_ok=True)

msgs = [
    {"sender": "남친", "text": "우리 그만 만나자", "is_mine": False},
    {"sender": "나", "text": "갑자기 무슨 소리야?", "is_mine": True},
    {"sender": "남친", "text": "나 다른 사람 생겼어", "is_mine": False},
    {"sender": "나", "text": "5년인데?", "is_mine": True},
]

from PIL import Image
base = Image.new("RGB", (1080, 1920), "#FFFFFF")
_render_chat_frame(base, msgs, layout, font_dir, out / "test.png", content_top=347)
print("OK:", (out / "test.png").exists())
EOF
```

## 5. 추천 commit message

```
feat: P5 채팅 캡처 — 카카오톡 대화 버블 씬 신규 SceneType 추가

LLM이 본문 대화를 chat_messages로 추출하면 is_mine 기준
좌(상대/회색+아바타) · 우(나/노란) 버블로 렌더링.
SceneType에 "chat" 추가, ScriptData 직렬화, director/processor 전 경로 배선.
```

## 6. DOC-MAP 기준 갱신한 문서 목록

- `docs/pipeline.md` — Phase 2(LLM chat_messages 추출) · Phase 8(chat SceneType 렌더) 추가 권장
- `docs/config.md` — layout.json scenes.chat · scene_policy.json scene_rules.chat 항목 추가 권장
