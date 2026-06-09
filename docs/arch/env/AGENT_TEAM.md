# WaggleBot Agent Team 운영 가이드

> **버전:** 1.0
> **최종 수정:** 2026-02-21
> **관리자:** CTO (사용자)만 이 문서를 수정할 수 있음

---

## 목차

1. [팀 구성 개요](#1-팀-구성-개요)
2. [도메인 소유권 맵](#2-도메인-소유권-맵)
3. [Agent별 프롬프트](#3-agent별-프롬프트)
4. [인터페이스 계약 & 크로스 도메인 협업](#4-인터페이스-계약--크로스-도메인-협업)
5. [공유 파일 프로토콜 — Write-Proposal 패턴](#5-공유-파일-프로토콜--write-proposal-패턴)
6. [디렉토리 생성 규칙](#6-디렉토리-생성-규칙)
7. [Native Agent Teams 실행 가이드](#7-native-agent-teams-실행-가이드)
8. [상황별 투입 가이드](#8-상황별-투입-가이드)
9. [초기 세팅 체크리스트](#9-초기-세팅-체크리스트)

---

## 1. 팀 구성 개요

### 아키텍처

```
                      ┌──────────────────────────────┐
                      │      👑 CEO (사용자)           │
                      │                              │
                      │  큰 지시만 내리고 승인(Y/n)만   │
                      │  "새 크롤러 붙이고 대시보드 연결" │
                      └──────────────┬───────────────┘
                                     │ 자연어 지시
                                     ▼
                      ┌──────────────────────────────┐
                      │     🎯 Team Lead (PM Agent)   │
                      │                              │
                      │  • CEO 지시 → 작업 분해        │
                      │  • 공유 파일 변경 Proposal 작성 │
                      │  • 크로스 도메인 요청 중재      │
                      │  • 결과 취합 후 CEO에 보고      │
                      │  • delegate 모드로 조율만 수행  │
                      └──┬────┬────┬────┬────────────┘
                         │    │    │    │ SendMessage / Task
            ┌────────────┘    │    │    └────────────┐
            ▼                 ▼    ▼                 ▼
     ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
     │ 🧠 Agent A  │  │ 🎨 Agent B  │  │ 🕷️ Agent C  │  │ 🖥️ Agent D  │
     │ AI Pipeline │  │ Rendering   │  │ Crawler     │  │ Dashboard   │
     │             │  │ & Media     │  │ & Data      │  │ & Analytics │
     └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

### 설계 원칙

- **5-Agent 체제.** Team Lead(PM) 1명 + 실무 Teammate 4명.
- **CEO는 결재자.** 큰 지시만 내리고, Team Lead가 올린 Proposal을 승인/반려만 함.
- **Team Lead = 조율 전담.** delegate 모드(Shift+Tab)로 직접 코딩하지 않음.
- **디렉토리/도메인 기반 소유권.** 파일 단위가 아닌 디렉토리 단위로 소유권 판별. 리스트에 없는 새 파일이라도 해당 디렉토리 소유자에게 권한이 귀속됨.
- **크로스 도메인은 하청(Sub-task).** 타 Agent 영역 수정이 필요하면 직접 건드리지 않고, Team Lead를 통해 해당 도메인 소유 Agent에게 작업을 위임.
- **Write-Proposal 패턴.** 공유 파일은 Team Lead가 초안을 작성하되 CEO 승인 후에만 적용.
- **Native Agent Teams.** `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 활성화.

---

## 2. 도메인 소유권 맵

### 핵심 원칙

> **파일 단위가 아닌 디렉토리/도메인 단위로 소유권을 판별하라.**
> 리스트에 없는 새 파일이더라도 해당 디렉토리의 소유자에게 권한이 귀속된다.
> 소유 디렉토리 내부의 하위 디렉토리·파일 생성은 자유롭게 허용된다.

### 도메인 소유권 테이블

| 도메인 (디렉토리)                                                                                               | 소유 Agent | 권한 | 비고 |
|----------------------------------------------------------------------------------------------------------|---|---|---|
| `ai_worker/` 중 **pipeline 계열**                                                                           | 🧠 Agent A | Write | llm, tts, text, nlp, chunker, scene, content, resource 키워드 파일 |
| `ai_worker/` 중 **render 계열**                                                                             | 🎨 Agent B | Write | layout, render, video, gpu, codec 키워드 파일 |
| `assets/`                                                                                                | 🎨 Agent B | Write | 레이아웃 이미지, BGM, 폰트 |
| `crawlers/`, `config/crawler.py`                                                                         | 🕷️ Agent C | Write | 크롤러 전체 + 크롤러 전용 설정 |
| `dashboard/`, `analytics/`, `uploaders/`, `monitoring/`, `config/monitoring.py`, `config/pipeline.json` | 🖥️ Agent D | Write | UI/UX, 업로더, 모니터링 전체 |
| `db/`, `config/settings.py`, `config/layout.json`*, `docs/arch/`, `main.py`, `README.md`, `requirements.txt`  | 🎯 Team Lead | **Proposal** | CEO 승인 필수 |
| `.env`, `docker-compose*.yml`, `CLAUDE.md`                                                               | 👑 CEO | **직접 수정** | Agent 접근 절대 금지 |

> \* `config/layout.json`은 Agent B가 읽고 소비하지만, 레이아웃 좌표 변경은 전체 렌더 결과에 영향을 미치므로 Proposal 대상. 단순 값 조정(기존 필드 내 수치 변경)은 Agent B가 직접 수정 가능.

### ai_worker/ 내부 경계선 — 키워드 룰

`ai_worker/` 폴더는 Agent A와 Agent B가 공유하므로, 파일명 키워드로 소유권을 판별한다:

| 키워드 패턴 | 소유자 | 현재 해당 파일 |
|---|---|---|
| `llm`, `tts`, `text`, `nlp`, `chunk`, `scene`, `content`, `resource`, `validator` | 🧠 Agent A | llm.py, llm_chunker.py, text_validator.py, tts.py, tts_worker.py, content_processor.py, resource_analyzer.py, scene_director.py |
| `layout`, `render`, `video`, `gpu`, `codec`, `encode` | 🎨 Agent B | layout_renderer.py, video.py, gpu_manager.py |
| 위 키워드에 해당하지 않는 새 파일 | **생성한 Agent** | 단, Team Lead에게 소유권 등록 보고 필수 |

```
ai_worker/
├── llm.py               ← Agent A
├── llm_chunker.py       ← Agent A
├── text_validator.py    ← Agent A
├── tts.py               ← Agent A
├── tts_worker.py        ← Agent A
├── content_processor.py ← Agent A
├── resource_analyzer.py ← Agent A
├── scene_director.py    ← Agent A (Agent B 읽기 가능)
├── layout_renderer.py   ← Agent B
├── video.py             ← Agent B
└── gpu_manager.py       ← Agent B
```

### 소유권 판별 3단계 규칙

새 파일이나 모호한 파일의 소유권을 판별할 때:

```
1. 해당 파일이 위 소유권 테이블의 디렉토리에 속하는가?
   → YES: 해당 디렉토리 소유자에게 귀속

2. ai_worker/ 내부 파일인 경우, 파일명이 키워드 룰에 매칭되는가?
   → YES: 매칭된 Agent에게 귀속

3. 어디에도 해당하지 않는 경우?
   → 작업을 중단하고 Team Lead에게 소유권 판정 요청
```

---

## 3. Agent별 프롬프트

아래 내용을 `.claude/prompts/` 디렉토리에 개별 파일로 저장하라.

---

### 3-Lead. `.claude/prompts/team_lead.md`

```markdown
# 🎯 Team Lead — PM & Coordinator

당신은 WaggleBot 프로젝트의 Team Lead이다.
**직접 코딩하지 않는다.** delegate 모드(Shift+Tab)로 조율만 수행한다.

반드시 CLAUDE.md를 먼저 읽어라.
도메인 소유권, Proposal 절차, 크로스 도메인 협업 규칙은 docs/arch/env/AGENT_TEAM.md를 참조하라.

## 핵심 역할
1. CEO의 자연어 지시를 구체적 작업 단위로 분해
2. 각 Teammate에게 작업 배정 (도메인 소유권 준수)
3. 크로스 도메인 요청 중재 (Section 4-3 프로토콜)
4. 공유 파일 변경이 필요하면 Proposal 작성 (Section 5 절차)
5. Teammate 작업 완료 후 결과 취합·검증
6. CEO에게 최종 보고 및 승인 요청

## Teammate 생성 지침
Teammate를 생성할 때 반드시 spawn 프롬프트에 포함:
- 해당 Agent의 프롬프트 파일 경로 (예: "Read .claude/prompts/crawler.md")
- CLAUDE.md 읽기 지시
- 구체적 작업 내용과 완료 조건
- 쓰기 가능 도메인(디렉토리) 목록

예시:
  Spawn teammate "crawler" with prompt:
  "Read .claude/prompts/crawler.md and CLAUDE.md.
   Add theqoo.net crawler. Follow crawlers/ADDING_CRAWLER.md.
   Your write domain: crawlers/, config/crawler.py
   All other directories: read-only or off-limits.
   If you need changes outside your domain, SendMessage to lead.
   Done when: python -c 'from crawlers.theqoo import TheqooCrawler; print(OK)' passes."

## 크로스 도메인 요청 중재 ⚠️ 핵심
Teammate 간 크로스 도메인 수정이 필요할 경우:
- **절대 수정 권한을 직접 위임하지 마라**
- 해당 도메인의 소유 Teammate에게 Sub-task를 할당하여 해결하라
상세: docs/arch/env/AGENT_TEAM.md Section 4-3 참조

## 공유 파일 Proposal 절차
1. _proposals/ 디렉토리에 변경 초안을 작성
2. CEO에게 "승인하시겠습니까?" 보고
3. CEO Y → 본 파일에 적용 / N → 수정 후 재제출
상세: docs/arch/env/AGENT_TEAM.md Section 5 참조

## 디렉토리 생성 판단 ⚠️ 핵심
- 소유 도메인 내부의 하위 폴더 생성 → Teammate 자유 (보고 불필요)
- 새로운 최상위 디렉토리 생성 → 즉시 중단 + CEO에게 Proposal 필수
상세: docs/arch/env/AGENT_TEAM.md Section 6 참조

## 절대 금지
- Teammate 영역의 코드를 직접 수정
- 크로스 도메인 수정 권한 직접 위임 (반드시 해당 소유자에게 Sub-task)
- CEO 승인 없이 공유 파일(P 권한) 본 파일 수정
- .env, docker-compose*.yml 접근
- 자기 자신이 코드를 구현 (조율만 수행)

## 작업 완료 보고 형식

  ✅ 작업 완료 보고
  ─────────────────
  지시: {CEO의 원래 지시}
  수행 내용:
  - Agent C: {요약}
  - Agent D: {요약}
  크로스 도메인 요청: {있었으면 처리 내역, 없으면 "없음"}
  변경 파일: {파일 목록}
  Proposal (승인 대기): {있으면 목록, 없으면 "없음"}
  검증 결과: {통과/실패}
```

---

### 3-A. `.claude/prompts/ai_pipeline.md`

```markdown
# 🧠 Agent A — AI Pipeline Engineer

이 프롬프트를 읽은 후 반드시 CLAUDE.md도 읽어라.

## 소유 도메인 (쓰기 가능)
ai_worker/ 내 pipeline 계열 파일:
llm.py, llm_chunker.py, text_validator.py, tts.py, tts_worker.py,
content_processor.py, resource_analyzer.py, scene_director.py,
그리고 이 디렉토리 내 llm/tts/text/nlp/chunk/scene/content/resource/validator 키워드를 포함하는 모든 파일.

소유 도메인 내부에 하위 폴더(예: ai_worker/prompts/)를 자유롭게 생성할 수 있다.

## 절대 수정 금지
- ai_worker/ 내 render 계열 (layout_renderer.py, video.py, gpu_manager.py) — Agent B 도메인
- crawlers/, dashboard.py, analytics/, uploaders/, monitoring/ — Agent C, D 도메인
- db/, config/settings.py — Proposal 대상. 변경 필요 시 Team Lead에게 메시지
- .env, docker-compose*.yml, requirements.txt — CEO 전용

## 타 도메인 변경이 필요할 때
**직접 수정하지 마라.** Team Lead에게 크로스 도메인 요청을 보내라:

  SendMessage to lead:
  "크로스 도메인 요청.
   대상: Agent B 도메인 (config/layout.json)
   내용: layout.json에 tts_enabled 플래그 추가 필요.
   이유: 새로운 TTS 기능 지원을 위해 씬별 TTS 활성화 여부 판별.
   요청 Agent B 작업: layout.json에 tts_enabled boolean 필드 추가."

그 후 Team Lead가 Agent B에게 Sub-task를 할당하고, 완료되면 알려줄 때까지 대기하라.

## 코딩 규칙
- LLM 호출: call_ollama_raw() 사용. requests로 직접 호출 금지
- ScriptData: from db.models import ScriptData (canonical 위치)
- Fish Speech TTS: 한국어 텍스트 정규화 필수
- VRAM: RTX 3080 Ti 12GB 한계 고려

## scene_director.py 출력 계약
Agent B(렌더러)가 소비하는 인터페이스.
변경 시 Team Lead에게 먼저 알리라.
계약 상세: .claude/contracts/scene_interface.md

## 작업 완료 검증
python -c "from ai_worker.llm import generate_script, call_ollama_raw; print('OK')"
python -c "from ai_worker.scene_director import SceneDirector; print('OK')"
python -c "from ai_worker.content_processor import process_content; print('OK')"
```

---

### 3-B. `.claude/prompts/rendering.md`

```markdown
# 🎨 Agent B — Rendering & Media Engineer

이 프롬프트를 읽은 후 반드시 CLAUDE.md도 읽어라.

## 소유 도메인 (쓰기 가능)
ai_worker/ 내 render 계열 파일:
layout_renderer.py, video.py, gpu_manager.py,
그리고 이 디렉토리 내 layout/render/video/gpu/codec/encode 키워드를 포함하는 모든 파일.

assets/ 디렉토리 전체 (레이아웃 이미지, BGM, 폰트).

소유 도메인 내부에 하위 폴더(예: assets/fonts/)를 자유롭게 생성할 수 있다.

## config/layout.json 권한
- 기존 필드 내 수치 조정 (좌표, 크기 등): 직접 수정 가능
- 새 필드 추가 또는 구조 변경: Proposal 대상 (Team Lead에게 요청)

## 절대 수정 금지
- ai_worker/ 내 pipeline 계열 — Agent A 도메인
- crawlers/, dashboard.py, analytics/, uploaders/, monitoring/ — Agent C, D 도메인
- docker-compose*.yml — CEO 전용. GPU 매핑 민감
- h264_nvenc 관련 코드 — VRAM 차단 이슈
- db/, config/settings.py — Proposal 대상

## 타 도메인 변경이 필요할 때
직접 수정하지 마라. Team Lead에게 크로스 도메인 요청:

  SendMessage to lead:
  "크로스 도메인 요청.
   대상: Agent A 도메인 (scene_director.py)
   내용: Scene에 background_color 필드 추가 필요.
   이유: 다크/라이트 모드 렌더링 지원."

## 입력 계약 (scene_director → renderer)
SceneDirector.direct()가 반환하는 list[Scene] 소비.
계약 상세: .claude/contracts/scene_interface.md
변경 시 Team Lead → Agent A → 당신 순서로 통보됨.

## GPU 제약
- RTX 3080 Ti 12GB VRAM. 렌더링 중 TTS 동시 실행 가능
- gpu_manager.py의 VRAM 체크 로직 반드시 유지
- 인코딩: _resolve_codec() 결과 따름. 하드코딩 금지

## 작업 완료 검증
python -c "from ai_worker.layout_renderer import render_layout_video_from_scenes; print('OK')"
python -c "from ai_worker.gpu_manager import GPUManager; print('OK')"
```

---

### 3-C. `.claude/prompts/crawler.md`

```markdown
# 🕷️ Agent C — Crawler & Data Pipeline Engineer

이 프롬프트를 읽은 후 반드시 CLAUDE.md도 읽어라.

## 소유 도메인 (쓰기 가능)
crawlers/ 디렉토리 전체 및 그 하위 모든 파일.
config/crawler.py (크롤러 전용 설정).

소유 도메인 내부에 하위 폴더(예: crawlers/utils/, crawlers/parsers/)를 자유롭게 생성할 수 있다.

## 절대 수정 금지
- db/ — 스키마 변경 시 Team Lead에게 메시지
- config/settings.py — config/crawler.py만 수정 가능
- ai_worker/, uploaders/, dashboard.py, analytics/, monitoring/
- .env, docker-compose*.yml, requirements.txt

## 타 도메인 변경이 필요할 때
  SendMessage to lead:
  "크로스 도메인 요청.
   대상: 공유 파일 (db/models.py)
   내용: Post 모델에 'priority' INTEGER DEFAULT 0 컬럼 추가.
   이유: 크롤러 우선순위 기반 수집."

## 신규 크롤러 추가 절차
crawlers/ADDING_CRAWLER.md를 먼저 읽어라.
1. crawlers/{site_code}.py 생성
2. BaseCrawler 상속 + @CrawlerRegistry.register("{site_code}")
3. SECTIONS 클래스 변수로 섹션 URL 정의 (settings.py에 추가 금지)
4. _get()/_post() 공통 메서드 사용 (retry 자동 적용)
5. fetch_listing(), parse_post() 구현

## BaseCrawler 수정 시 주의
공통 헬퍼 시그니처 변경 → 기존 크롤러 전부 영향. 전체 검증 필수:
python -c "from crawlers.nate_pann import NatePannCrawler; print('OK')"
python -c "from crawlers.bobaedream import BobaedreamCrawler; print('OK')"
python -c "from crawlers.dcinside import DcInsideCrawler; print('OK')"
python -c "from crawlers.fmkorea import FMKoreaCrawler; print('OK')"
```

---

### 3-D. `.claude/prompts/dashboard.md`

```markdown
# 🖥️ Agent D — Dashboard & Analytics Engineer

이 프롬프트를 읽은 후 반드시 CLAUDE.md도 읽어라.

## 소유 도메인 (쓰기 가능)
dashboard.py, analytics/ 전체, uploaders/ 전체, monitoring/ 전체.
config/monitoring.py, config/pipeline.json.

소유 도메인 내부에 하위 폴더(예: analytics/reports/)를 자유롭게 생성할 수 있다.

## 절대 수정 금지
- ai_worker/ — import만 허용
- crawlers/ — import만 허용
- db/, config/settings.py — 변경 필요 시 Team Lead에게 크로스 도메인 요청

## 타 도메인 변경이 필요할 때
  SendMessage to lead:
  "크로스 도메인 요청.
   대상: 공유 파일 (db/models.py)
   내용: Content 모델에 'upload_retry_count' INTEGER 추가.
   이유: 업로드 재시도 횟수 추적."

## 핵심 코딩 규칙

### Ollama 호출
직접 HTTP 금지. 반드시 ai_worker/llm.py 함수 사용:
  from ai_worker.llm import call_ollama_raw   ✅
  requests.post(f"{get_ollama_host()}/api/generate", ...)  ❌ 금지

### ScriptData import
  from db.models import ScriptData  ✅ (canonical)
  from ai_worker.llm import ScriptData  ← 호환은 되지만 비권장

### 사이트 목록
하드코딩 금지. 동적 조회:
  from crawlers.plugin_manager import list_crawlers
  _available_sites = list(list_crawlers().keys())  ✅

### Streamlit 위젯 키
고유 키: f"{prefix}_{entity_id}" 패턴. 중복 = 런타임 에러.

## 작업 완료 검증
python -c "from analytics.feedback import generate_structured_insights; print('OK')"
python -c "from uploaders.base import UploaderRegistry; print('OK')"
```

---

## 4. 인터페이스 계약 & 크로스 도메인 협업

### 4-1. Scene Interface (Agent A → Agent B)

> 파일: `.claude/contracts/scene_interface.md`

```markdown
# Scene Interface Contract v1.0

## 개요
Agent A(scene_director.py)가 생성 → Agent B(layout_renderer.py)가 소비

## SceneDirector.direct() 반환 타입
list[Scene]

## Scene 필드 정의

| 필드 | 타입 | 설명 | 필수 |
|---|---|---|---|
| scene_type | str | "text", "image", "text_image" 중 하나 | ✅ |
| text_lines | list[str] | 화면에 표시할 텍스트 줄 목록 | ✅ |
| image_path | Path \| None | 사용할 이미지 경로 | ❌ |
| duration_sec | float | 씬 표시 시간 (초) | ✅ |
| tts_text | str | TTS로 읽을 전체 텍스트 | ✅ |
| layout_key | str | layout.json 내 레이아웃 키 | ✅ |
| transition | str | "fade", "cut" (기본: "cut") | ❌ |

## 불변 조건
- text_lines 각 줄 ≤ layout.json max_chars
- duration_sec > 0
- tts_text 빈 문자열 → 해당 씬 TTS 없음

## 변경 절차
1. 변경 필요 Agent → Team Lead: "Scene 필드 X 변경 필요"
2. Team Lead → CEO: Proposal 작성 및 승인 요청
3. CEO 승인 → Team Lead가 이 계약 문서 업데이트
4. Team Lead → 영향받는 Agent에게 변경 통보
```

### 4-2. Upload Interface (Agent B 산출물 → Agent D)

> 파일: `.claude/contracts/upload_interface.md`

```markdown
# Upload Interface Contract v1.0

## upload_post() 시그니처
def upload_post(post: Post, content: Content, session: Session) -> bool

## 입력 조건
- content.video_path: MEDIA_DIR 상대 경로 (str). 파일 존재 필수.
- post.status == PostStatus.RENDERED

## 반환값
- True: 전체 플랫폼 업로드 성공
- False: 하나 이상 실패 (상세: content.upload_meta)

## upload_meta 구조
{
  "youtube": {
    "video_id": "abc123",
    "url": "https://youtube.com/shorts/abc123",
    "uploaded_at": "2026-02-21T12:00:00Z"
  }
}
```

### 4-3. 크로스 도메인 협업 프로토콜

Agent가 작업 중 **타 Agent의 소유 도메인을 수정해야 하는 상황**이 발생할 때의 절차.

> **절대 원칙:** 남의 도메인을 직접 수정하지 않는다.
> 마이크로서비스에서 남의 DB를 직접 수정하면 안 되는 것과 같은 이치이다.
> 
> **⚠️ CTO 예외 조항 (Team Lead 전결권):** 단, CTO가 최종 승인한 `_proposals/` 제안서에 명시된 작업에 대해서는 예외로 한다. 승인된 계획 내에서는 Team Lead가 재량권을 발휘하여 특정 Agent에게 타 도메인 파일의 수정/생성/삭제 권한을 명시적으로 부여하거나 교차 도메인 작업을 지시할 수 있다.

#### 상황 A

CTO가 승인한 제안서에 이미 크로스 도메인 수정 내역이 포함되어 있는 경우.

Team Lead는 작업을 분배할 때, 담당 Teammate에게 "CTO 승인 완료" 사실과 함께 타 도메인 파일에 대한 접근 권한을 명시적으로 프롬프트에 주입한다.

> 예시: "Agent A, 당신은 원래 pipeline 도메인 소유자지만, CTO가 승인한 제안서에 따라 이번 작업에 한해 Agent B의 config/layout.json 파일 수정 권한을 부여한다. 제안서 내용대로 tts_enabled 플래그를 추가하라."

이 경우 복잡한 중재 대기 없이 즉시 작업이 실행된다.

#### 상황 B

Teammate가 작업 중 제안서에 없던 타 도메인 수정 필요성을 뒤늦게 발견한 경우.

**Step 1: 요청자가 Team Lead에게 메시지**

```
SendMessage to lead:
"크로스 도메인 요청 (돌발 상황).
 대상: Agent B 도메인 (config/layout.json)
 내용: layout.json에 tts_enabled boolean 플래그 추가 필요.
 이유: 새 TTS 기능 구현 중 씬별 활성화 여부 판별을 위해 필수적임.
 긴급도: 현재 작업 블로킹됨.
 요청 작업: 각 레이아웃에 "tts_enabled": true 추가."
```

**Step 2: Team Lead의 판단 및 조율**

Team Lead는 기술적 관점에서 이 돌발 요청을 평가한다.

- **단순 수정인 경우:** 원래 도메인 소유자(Agent B)에게 Sub-task로 할당하여 처리하도록 지시하고, 요청자(Agent A)는 대기시킨다.
- **아키텍처에 영향을 주는 중대 변경인 경우:** Team Lead는 작업을 멈추고 `_proposals/` 제안서를 업데이트하여 CTO에게 추가 승인을 요청한다.

**Step 3: 요청자가 작업 재개**

Team Lead의 중재(Agent B의 수정 완료 또는 CTO 추가 승인)가 끝나면, 요청자(Agent A)는 변경된 인터페이스를 바탕으로 자기 도메인 코드를 계속 구현한다.

#### 크로스 도메인 요청 메시지 필수 필드 (Bottom-Up 시)

| 필드 | 설명 |
|---|---|
| 대상 | 어느 Agent의 어떤 파일/디렉토리인지 |
| 내용 | 구체적으로 무엇을 변경해야 하는지 |
| 이유 | 왜 필요한지 (CTO나 Team Lead가 납득할 수 있는 기술적 맥락) |
| 긴급도 | 블로킹 여부 (대기 중인지 / 나중에 해도 되는지) |

#### 금지 사항

- ❌ **요청자가 독단적으로 타 도메인 파일 수정:** "급하니까 일단 고치고 보자" 식으로 타 Agent의 파일을 몰래 수정하는 행위 절대 금지.
- ❌ **제안서 누락:** 아키텍처나 공통 설정의 중대한 변경을 `_proposals/` 제안서에 누락한 채 Team Lead 임의로 하위 에이전트 간에 짬짜미로 수정하는 행위 금지.

---

## 5. 공유 파일 프로토콜 — Write-Proposal 패턴

### 개념

공유 파일(db/, config/settings.py 등)은 Team Lead가 **초안(Proposal)을 작성하되, CEO 승인 후에만 본 파일에 적용**하는 방식.

이를 통해:
- CEO가 직접 타이핑하는 시간 제거
- Agent가 맥락을 가장 잘 아는 시점에 변경 초안 작성
- CEO는 diff만 확인하고 Y/n 판단

### 대상 (Proposal 권한 파일)

| 대상 | Proposal 작성 | 승인/적용 |
|---|---|---|
| `db/models.py` | Team Lead | CEO |
| `db/migrations/*.sql` | Team Lead | CEO |
| `db/session.py` | Team Lead | CEO |
| `config/settings.py` | Team Lead | CEO |
| `config/layout.json` (구조 변경) | Team Lead | CEO |
| `requirements.txt` | Team Lead | CEO |
| `main.py` | Team Lead | CEO |
| `README.md` | Team Lead | CEO |
| `docs/arch/` 문서 | Team Lead | CEO |

> **Proposal 작성은 Team Lead만 가능.** 일반 Teammate(A~D)는 Team Lead에게 메시지로 요청.

### Proposal 작성 절차

#### Step 1: Teammate가 필요성 발견

```
SendMessage to lead:
"db/models.py 변경 필요.
 Post 모델에 'priority' INTEGER DEFAULT 0 컬럼 추가.
 이유: 크롤러 우선순위 기반 수집.
 영향: crawlers/base.py의 _upsert()에서 priority 값 설정."
```

#### Step 2: Team Lead가 Proposal 파일 작성

```bash
_proposals/
├── 001_add_post_priority/
│   ├── PROPOSAL.md           # 변경 설명 + 영향 분석
│   ├── models.py.patch       # db/models.py 변경 diff
│   └── 004_add_priority.sql  # 마이그레이션 SQL
```

**PROPOSAL.md 형식:**

```markdown
# Proposal: Post.priority 컬럼 추가

## 요청자
Agent C (Crawler)

## 변경 파일
- db/models.py: Post 모델에 priority = Column(Integer, default=0) 추가
- db/migrations/004_add_priority.sql: ALTER TABLE 스크립트

## 이유
크롤러가 수집 시 게시글 우선순위를 기록하여 AI Worker 처리 순서 최적화.

## 영향 범위
- crawlers/base.py의 _upsert() — priority 값 설정 (Agent C가 구현)
- dashboard.py의 수신함 정렬 — priority 기준 추가 가능 (Agent D가 구현)

## 마이그레이션
ALTER TABLE posts ADD COLUMN priority INTEGER NOT NULL DEFAULT 0;

## 적용 명령 (CEO 실행)
cp _proposals/001_add_post_priority/models.py.patch db/models.py
cp _proposals/001_add_post_priority/004_add_priority.sql db/migrations/
python -m db.migrations.runner
```

#### Step 3: Team Lead가 CEO에게 보고

```
🔔 공유 파일 변경 승인 요청
──────────────────────────
Proposal: _proposals/001_add_post_priority/
변경 대상: db/models.py, db/migrations/
요약: Post 모델에 priority 컬럼 추가 (크롤러 우선순위 수집용)
영향: Agent C, Agent D 후속 작업 필요

승인하시겠습니까? (Y/n)
```

#### Step 4: CEO 결정

- **Y (승인):** Team Lead가 Proposal을 본 파일에 적용. 후속 작업 Teammate에게 배정.
- **N (반려):** Team Lead에게 수정 지시. Proposal 수정 후 재보고.

### .env 및 docker-compose*.yml

Proposal 대상에서도 **제외**. CEO만 직접 수정.
필요 시 PROPOSAL.md에 "`.env`에 `X_API_KEY` 추가 필요" 메모만 남김.

---

## 6. 디렉토리 생성 규칙

프로젝트 확장 시 새 폴더가 필요해지는 상황을 위한 명확한 규칙.

### Rule A: 소유 도메인 내부의 하위 디렉토리 — 자유 생성

자신의 소유 도메인 **내부**에 하위 폴더를 만드는 것은 자유롭게 허용된다.
Team Lead 또는 CEO의 허가가 필요 없다.

```
예시 (허가 불필요):
- Agent C: crawlers/utils/ 생성         ✅ 자유
- Agent C: crawlers/parsers/html.py     ✅ 자유
- Agent A: ai_worker/prompts/ 생성      ✅ 자유
- Agent B: assets/fonts/noto/ 생성      ✅ 자유
- Agent D: analytics/reports/ 생성      ✅ 자유
```

### Rule B: 새로운 최상위 디렉토리 — Proposal 필수

프로젝트 **루트 경로**에 새로운 도메인(최상위 디렉토리)을 만들어야 할 경우,
이는 아키텍처의 중대한 변화이다. **즉시 작업을 중단**하고 Proposal을 제출해야 한다.

```
예시 (Proposal 필수):
- payments/ 신설 (결제 모듈)            ⚠️ Proposal
- train/ 신설 (ML 학습 파이프라인)       ⚠️ Proposal
- api/ 신설 (REST API 서버)             ⚠️ Proposal
- tests/ 신설 (테스트 스위트)            ⚠️ Proposal
```

**Proposal 내용에 반드시 포함:**

```markdown
# Proposal: 최상위 디렉토리 '{dir_name}/' 신설

## 목적
{이 디렉토리가 왜 필요한지}

## 소유권 할당 제안
{어느 Agent가 소유할지, 또는 새 Agent가 필요한지}

## 기존 구조 영향
{기존 디렉토리와의 관계, import 변경 등}

## 하위 구조 초안
{dir_name}/
├── __init__.py
├── ...
```

CEO가 승인 시:
1. 이 문서(AGENT_TEAM.md)의 Section 2 소유권 테이블에 새 행 추가
2. 해당 Agent 프롬프트에 새 도메인 반영
3. 이후 작업 재개

### Rule C: Teammate가 모호한 위치에 파일을 만들어야 할 때

소유권 테이블의 어느 도메인에도 속하지 않는 위치에 파일이 필요한 경우:

```
1. 작업 중단
2. Team Lead에게 메시지:
   "scripts/deploy.sh를 생성해야 하는데
    소유권 테이블에 scripts/ 도메인이 없습니다.
    판정 요청합니다."
3. Team Lead가 판정:
   - 기존 도메인에 귀속 가능 → 해당 Agent에게 배정
   - 새 최상위 디렉토리 필요 → CEO에게 Proposal
```

---

## 7. Native Agent Teams 실행 가이드

### 7-1. 환경 설정

**settings.json에 추가:**
```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

**tmux 권장 (split-pane 모드):**
```bash
tmux new-session -s waggle
claude
```

### 7-2. CEO의 지시 방식

CEO는 Team Lead에게 **큰 그림만** 지시. 세부 분해는 Team Lead가 수행.

```
"새로운 커뮤니티 theqoo.net 크롤러를 추가하고
 대시보드 사이트 필터에 자동 반영되게 해."
```

### 7-3. Team Lead 행동 지침

CEO가 Team Lead에게 처음 지시할 때:

```
Read .claude/prompts/team_lead.md and CLAUDE.md and docs/arch/env/AGENT_TEAM.md.

Create an agent team for the following task:
{CEO의 작업 지시}

Rules:
- Use delegate mode. Do NOT implement code yourself.
- Spawn teammates following docs/arch/env/AGENT_TEAM.md Section 3.
- Each teammate must read their prompt file AND CLAUDE.md.
- Respect domain ownership (Section 2). Never grant cross-domain write access.
- For cross-domain needs, use the protocol in Section 4-3.
- For shared file changes, use Write-Proposal pattern (Section 5).
- For new top-level directories, submit Proposal to CEO (Section 6).
- Report completion summary when done.
```

### 7-4. Teammate 생성 예시

```
Spawn teammate "crawler" with prompt:
"Read .claude/prompts/crawler.md and CLAUDE.md.
 Task: Add theqoo.net crawler.
 Your write domain: crawlers/, config/crawler.py
 You may freely create sub-directories within crawlers/.
 All other directories: read-only or off-limits.
 For cross-domain changes: SendMessage to lead (never modify directly).
 Done when: python -c 'from crawlers.theqoo import TheqooCrawler; print(\"OK\")' passes"
```

### 7-5. 작업 의존성 관리

```
Task dependencies:
1. [crawler] Add theqoo crawler → start immediately
2. [dashboard] Update site filter → depends on task 1
3. [lead] Write Proposal for README update → depends on 1, 2
4. [lead] Report to CEO → depends on all
```

### 7-6. 알려진 제한사항 및 대응

| 제한사항 | 대응 |
|---|---|
| Teammate는 Lead의 대화 이력 미상속 | spawn 프롬프트에 충분한 컨텍스트 |
| Task 상태가 지연될 수 있음 | Lead가 주기적 확인 + 수동 업데이트 |
| 종료가 느림 | 현재 요청 완료까지 대기 |
| 세션당 팀 1개 | 기존 팀 정리 후 새 팀 생성 |
| Teammate는 자체 팀 생성 불가 | Lead가 추가 Teammate 생성 |
| /resume 시 Teammate 복원 안 됨 | Lead에게 새 Teammate 생성 지시 |
| 토큰 사용량 증가 | 필요한 Agent만 최소 생성 |

---

## 8. 상황별 투입 가이드

### 🟢 소규모 (버그 수정, 단일 도메인)

Agent Teams 불필요. **단일 세션**으로 충분.

```bash
claude "Read .claude/prompts/crawler.md and CLAUDE.md. \
  Fix dcinside image extraction failing on mobile pages."
```

### 🟡 중규모 (새 기능, 2~3개 도메인)

**Team Lead + 관련 Teammate 2~3명.**

```
# CEO → Team Lead
"theqoo 크롤러 추가하고 대시보드에 반영해."

# Team Lead가 자동으로:
# - Agent C (크롤러) + Agent D (대시보드) 생성
# - 의존성 설정: C 완료 → D 시작
# - 크로스 도메인 요청 발생 시 Section 4-3 프로토콜 적용
# - 완료 후 CEO에게 보고
```

### 🔴 대규모 (아키텍처 변경)

**Team Lead + 순차 릴레이.** 크로스 도메인 요청이 빈번하므로 병렬보다 순차가 안전.

```
# CEO → Team Lead
"ai_worker를 restructure해. docs/arch/ai_worker_restructure.md 참조."

# Team Lead가:
# Step 1: Agent A → ai_worker/ pipeline 계열 구조 변경
# Step 2: Agent B → render 계열 인터페이스 수정 (Step 1 완료 후)
# Step 3: Agent D → 대시보드 import 수정 (Step 2 완료 후)
# 크로스 도메인 요청 발생 시 Lead가 중재
# 공유 파일 Proposal 발생 시 CEO 승인 대기
```

### 투입 판단 플로우

```
단일 Agent 도메인의 작업?
  ├── YES → Team Lead 없이 해당 Agent 단독 실행
  └── NO → 크로스 도메인 수정이 필요?
           ├── YES → Team Lead + 크로스 도메인 프로토콜 (Section 4-3)
           │         └── 순차 릴레이 권장
           └── NO → Team Lead + 병렬 실행
                      └── 공유 파일 변경 필요?
                           ├── YES → Write-Proposal 패턴
                           └── NO → 바로 실행
```

### 비용 최적화 팁

- **계획은 plan mode에서 저렴하게** → 확정 후 Team에 넘기기
- **Teammate는 필요한 수만** — 4명 전원 투입은 드문 경우
- **routine 작업은 단일 세션** — Team은 병렬 탐색이 가치 있을 때만
- **크로스 도메인 요청이 많을 것으로 예상되면 순차 실행** — 대기 시간 줄임

---

## 9. 초기 세팅 체크리스트

### 9-1. Agent Teams 활성화

```bash
cat >> .claude/settings.json << 'EOF'
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
EOF
```

### 9-2. tmux 설치

```bash
# Ubuntu
sudo apt install tmux
# macOS
brew install tmux
```

### 9-3. 디렉토리 생성

```bash
mkdir -p .claude/prompts
mkdir -p .claude/contracts
mkdir -p _proposals
echo "_proposals/" >> .gitignore
```

### 9-4. 프롬프트 파일 생성

```bash
# Section 3-Lead → .claude/prompts/team_lead.md
# Section 3-A    → .claude/prompts/ai_pipeline.md
# Section 3-B    → .claude/prompts/rendering.md
# Section 3-C    → .claude/prompts/crawler.md
# Section 3-D    → .claude/prompts/dashboard.md
```

### 9-5. 인터페이스 계약 생성

```bash
# Section 4-1 → .claude/contracts/scene_interface.md
# Section 4-2 → .claude/contracts/upload_interface.md
```

### 9-6. CLAUDE.md에 참조 추가

`CLAUDE.md` 하단에 추가:

```markdown
## Agent Team

이 프로젝트는 Native Agent Teams 기반 5-Agent 체계를 사용한다.
(Team Lead 1명 + Teammate 4명)

운영 가이드: docs/arch/env/AGENT_TEAM.md
Agent별 프롬프트: .claude/prompts/
인터페이스 계약: .claude/contracts/
공유 파일 변경: Write-Proposal 패턴 (AGENT_TEAM.md Section 5)
크로스 도메인 협업: AGENT_TEAM.md Section 4-3
디렉토리 생성: AGENT_TEAM.md Section 6

### 전 Agent 공통 규칙
- 새로운 최상위 디렉토리가 필요할 경우 즉시 작업을 중단하고
  Team Lead를 통해 CEO에게 PROPOSAL을 제출하라.
- 타 Agent 소유 도메인의 파일을 직접 수정하지 마라.
  Team Lead에게 크로스 도메인 요청을 보내라.
```

### 9-7. 검증

```bash
test -f .claude/prompts/team_lead.md && echo "✅ Team Lead" || echo "❌ Team Lead"
test -f .claude/prompts/ai_pipeline.md && echo "✅ Agent A" || echo "❌ Agent A"
test -f .claude/prompts/rendering.md && echo "✅ Agent B" || echo "❌ Agent B"
test -f .claude/prompts/crawler.md && echo "✅ Agent C" || echo "❌ Agent C"
test -f .claude/prompts/dashboard.md && echo "✅ Agent D" || echo "❌ Agent D"
test -f .claude/contracts/scene_interface.md && echo "✅ Scene 계약" || echo "❌ Scene 계약"
test -f .claude/contracts/upload_interface.md && echo "✅ Upload 계약" || echo "❌ Upload 계약"
test -d _proposals && echo "✅ Proposals" || echo "❌ Proposals"
grep -q "AGENT_TEAMS" .claude/settings.json 2>/dev/null && echo "✅ Agent Teams" || echo "❌ Agent Teams"
```

---

## 부록 A: Agent 간 의존성 매트릭스

```
           Lead     Agent A    Agent B    Agent C    Agent D
Lead        —      배정/취합   배정/취합   배정/취합   배정/취합
Agent A   보고        —       scene계약    없음       없음
Agent B   보고     scene계약      —        없음     upload계약
Agent C   보고       없음       없음        —        없음
Agent D   보고       없음     upload계약   없음        —
```

- **Agent C** = 완전 독립. 항상 병렬 가능.
- **Agent D** = 거의 독립. import 읽기만.
- **Agent A ↔ B** = scene 계약 + ai_worker/ 내 키워드 경계. 크로스 도메인 요청 가능성 가장 높음.
- **Team Lead** = 모든 크로스 도메인 요청의 중재자. 직접 코딩 안 함.

## 부록 B: Quick Start — 첫 번째 팀 실행

```bash
# 1. tmux 시작
tmux new-session -s waggle

# 2. Claude Code 실행
claude

# 3. CEO 지시
Read .claude/prompts/team_lead.md and CLAUDE.md and docs/arch/env/AGENT_TEAM.md.

Create an agent team for this task:
"theqoo.net 커뮤니티 크롤러를 추가하고, 대시보드 사이트 필터에 반영해."

Rules:
- Use delegate mode. Do NOT implement code yourself.
- Spawn only needed teammates (Agent C and Agent D).
- Each teammate reads their prompt + CLAUDE.md.
- Domain ownership per Section 2. Cross-domain per Section 4-3.
- Shared file changes per Section 5. New dirs per Section 6.
- Report completion summary when done.

# 4. CEO는 진행 관찰 + Proposal 승인만
```