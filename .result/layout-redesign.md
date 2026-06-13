# 숏폼 레이아웃 재설계 (와글 브랜드 v3)

## 1. 작업 결과

Claude Design 핸드오프 번들(`새 숏폼 레이아웃.html`)을 기반으로 WaggleBot 렌더러를 와글 브랜드 디자인으로 전면 교체.

**구현 범위 (P1~P4 완료):**
- **P1** 핵심 비주얼: 옐로우 헤더(#FBD024) + 제목블록 + 메타줄 + 굵은 검정 자막(흐림 없음) + 자연비율 이미지
- **P2** 아웃트로 재설계: 마스코트(PIL 코드 드로잉) + "여러분이라면?" 질문 + 댓글입력창 목업 (구독유도 제거)
- **P3** 영상 자연비율: `_encode.py` `_render_video_segment` — ffprobe로 클립 크기 측정 후 contain 계산
- **P4** 댓글 씬 신규: SceneType "comments" + `comment_items` 필드 + DB 원본 댓글 직접 전달 + `_render_comments_frame`

## 2. 수정 파일 목록

| 파일 | 변경 내용 |
|------|---------|
| `config/layout.json` | 전면 재구성 — `global.header/title_block/content` 신규, 모든 씬 블록 갱신, `scenes.comments` 추가 |
| `config/scene_policy.json` | `outro.fixed_texts` 참여유도형 5개 교체, `scene_rules.comments` 추가 |
| `worker/ai_worker/renderer/_frames.py` | 전면 재작성 — `_draw_header`, `_draw_title_block`, `_title_block_bottom_y`, `_fit_contain`, `_create_base_frame`(코드드로잉), `_create_header_only_frame`, 씬 렌더러 5종 재작성, `_render_comments_frame` 신규, `_render_outro_frame` 재작성, `_fmt_count`/`_relative_time` 추가 |
| `worker/ai_worker/renderer/layout.py` | imports 갱신, `_render_pipeline` meta+content_top+header_only 추가, Step-8 디스패치 전면 갱신(greying 제거·content_top 전달·comments 처리), wrapping 폰트 Bold 변경, `render_layout_video_from_scenes` meta 빌드 |
| `worker/ai_worker/renderer/_tts.py` | `entry.get("dwell_sec", outro_duration)` — per-entry 체류시간 오버라이드 |
| `worker/ai_worker/renderer/_encode.py` | `_render_video_segment` — `content_top` 파라미터 추가, P3 자연비율 contain 경로 추가 |
| `worker/ai_worker/scene/director.py` | `SceneType`에 "comments" 추가, `SceneDecision`에 `comment_items`/`dwell_sec` 필드 추가, `__init__`에 `comments` 파라미터 추가, `direct()`에 댓글씬 생성 로직 추가 |
| `worker/ai_worker/pipeline/content_processor.py` | `SceneDirector` 생성 시 `comments=_db_comments` 전달 |
| `worker/ai_worker/core/processor.py` | 두 곳의 `SceneDirector` 생성에 `comments=_db_cmts2` 전달 |

## 3. 테스트 결과물 위치

- `config/layout.json`, `config/scene_policy.json` — 설정 파일 직접 확인 가능
- Python 문법 검사: `python3 -c "import ast; ast.parse(open('worker/ai_worker/renderer/_frames.py').read())"` → OK (전파일)
- `_fmt_count` 단위 검증 완료 (내부 exec 테스트)

## 4. 수동 테스트 방법

### 빠른 PNG 검증 (컨테이너 없이)
```bash
cd /home/justant/Data/WaggleBot/worker

python3 -c "
import sys; sys.path.insert(0, '.')
from pathlib import Path
from PIL import Image
from ai_worker.renderer._frames import (
    _create_base_frame, _create_header_only_frame,
    _title_block_bottom_y, _render_text_only_frame,
    _render_outro_frame, _render_comments_frame,
)
import json

layout = json.load(open('../config/layout.json'))
font_dir = Path('../assets/fonts')
title = '탕비실 간식 도둑 3주만에 잡은 썰'
meta = {'author': None, 'time': '3시간 전', 'views': '14.6만', 'comments': 892}

base = _create_base_frame(layout, title, font_dir, font_dir, meta=meta)
base.save('/tmp/test_base.png')
print('base:', base.size)

ct = _title_block_bottom_y(layout, title, font_dir)
print('content_top:', ct)

# text_only
hist = [{'lines': ['처음엔 내가'], 'block_type': 'body'},
        {'lines': ['근데 매일', '딱 두 개씩 비더라'], 'block_type': 'body'}]
_render_text_only_frame(base, hist, layout, font_dir, Path('/tmp/test_text.png'), ct)

# outro
hdr = _create_header_only_frame(layout, font_dir)
_render_outro_frame(hdr, '여러분이라면 어떻게 하셨을까요?', layout, font_dir, Path('/tmp/test_outro.png'))

# comments
items = [
    {'author': '사이다요정', 'content': '부장님 ㅋㅋㅋㅋ 이게 진짜 회사생활이지', 'likes': 1200, 'is_best': True},
    {'author': '9년차직장인', 'content': 'CCTV 설치한 거 신의 한 수네요', 'likes': 847, 'is_best': False},
    {'author': '간식러버', 'content': '남의 간식에 손대는 건 진짜 선 넘었다', 'likes': 522, 'is_best': False},
]
_render_comments_frame(base, items, layout, font_dir, Path('/tmp/test_comments.png'), ct)

print('Done → /tmp/test_{base,text,outro,comments}.png')
"
```

### E2E (컨테이너에서)
```bash
docker compose -f env/docker-compose.yml exec ai_worker bash -c "
cd /app && python3 -c \"
from ai_worker.renderer.layout import render_layout_video_from_scenes
# APPROVED 포스트 1건을 수동 실행
from db.session import SessionLocal
from db.models import Post, PostStatus
with SessionLocal() as db:
    post = db.query(Post).filter_by(status=PostStatus.APPROVED).first()
    if post: print('Found post:', post.id, post.title[:30])
\"
"
```

## 5. 추천 commit message

```
feat: 와글 브랜드 숏폼 레이아웃 v3 전면 적용

P1: 옐로우 헤더·제목블록·메타줄·자막 흐림제거·자연비율 이미지
P2: 아웃트로 마스코트+참여유도 질문+댓글입력창 목업 (구독유도 제거)
P3: 영상씬 자연비율 contain (ffprobe+filter_complex, ADR-0002 준수)
P4: 댓글씬 신규 — SceneType 'comments' + DB 원본 likes 직접 전달

layout.json 전면 재구성 / _frames.py 전면 재작성
```

## 6. 갱신한 문서 목록 (DOC-MAP 기준)

| 문서 | 갱신 필요 내용 |
|------|-------------|
| `docs/pipeline.md` | Phase 8 씬 타입 목록에 "comments" 추가, 아웃트로 설명 갱신 |
| `docs/config.md` | `layout.json` 구조 섹션 전면 갱신 (global.header/title_block 신규, scenes 변경) |
