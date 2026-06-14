# WaggleBot — 시스템 컨텍스트 (L1)

> last-verified: 2026-06-12 (commit `656dffd`) · code-ref: 전역
> scope: 시스템 외부 경계, 행위자, 전체 흐름 — SSOT

커뮤니티 게시글을 자동 크롤링해 LLM 대본 → TTS → LTX-2 비디오 → FFmpeg 렌더링 → YouTube 자동 업로드까지 처리하는 AI 콘텐츠 자동화 파이프라인.

## 전체 시스템 흐름

```mermaid
flowchart TD
    subgraph External["외부 소스"]
        NATE[네이트판]
        DCINSIDE[디씨인사이드]
        FMKOREA[에펨코리아]
        BOBAEDREAM[보배드림]
    end

    subgraph Crawler["크롤러 (Python)"]
        CRAWL[crawler 서비스<br/>CrawlerRegistry + Plugin]
    end

    subgraph Storage["데이터 저장"]
        DB[(MariaDB 11<br/>wagglebot DB)]
    end

    subgraph Backend["백엔드 (Java)"]
        SPRING[Spring Boot 3.3<br/>REST API :8080]
        JOB[Job Queue<br/>jobs 테이블]
    end

    subgraph Frontend["프론트엔드 (Next.js)"]
        DASH[대시보드 :3000<br/>수신함/편집실/갤러리<br/>분석/설정]
    end

    subgraph AI_Pipeline["AI 파이프라인 (Python)"]
        AI[ai_worker<br/>8-Phase Pipeline]
        DW[dashboard_worker<br/>Jobs 폴링 데몬]
    end

    subgraph LLM["LLM 백엔드 (cli 또는 api)"]
        LLM_W[llm-worker<br/>Java :8090<br/>Claude CLI subprocess]
        CLAUDE_CLI[Claude CLI<br/>haiku / sonnet]
        ANTHROPIC_API[Anthropic API<br/>직접 호출]
    end

    subgraph GPU_Services["GPU 서비스 (RTX 3090)"]
        FISH[OpenAudio S1-mini<br/>TTS :8082]
        COMFY[ComfyUI<br/>LTX-2 Video :8188]
    end

    subgraph Upload["업로더"]
        YT[YouTube API]
    end

    subgraph Monitoring["운영"]
        MON[monitoring 서비스<br/>헬스체크/알림]
        TG[telegram-bridge<br/>:3847]
    end

    External --> CRAWL
    CRAWL --> DB
    DB --> SPRING
    SPRING --> JOB
    JOB --> DW
    DW --> AI
    AI --> LLM_W
    LLM_W --> CLAUDE_CLI
    AI --> FISH
    AI --> COMFY
    AI --> DB
    SPRING --> DASH
    AI --> Upload
    MON --> DB
    TG --> SPRING
```

## 행위자 및 외부 시스템

| 행위자 / 시스템 | 역할 |
|---------------|------|
| 운영자 (관리자) | 대시보드에서 게시글 승인/거절, 설정 변경 |
| 커뮤니티 사이트 | 원시 게시글·댓글 공급 (네이트판·디씨·에펨코리아·보배드림 등) |
| Claude API (Anthropic) | LLM 추론 — 대본 생성·씬 지시·번역·피드백 분석 |
| YouTube Data API | 최종 영상 업로드, 조회수/성과 데이터 수집 |
| Telegram Bot API | 운영자 원격 제어 인터페이스 (선택) |

> 상세 배포 구성(포트·볼륨·환경변수) → [`docs/20-containers/topology.md`](../20-containers/topology.md)
> 8-Phase AI 파이프라인 책임 → [`docs/30-components/pipeline.md`](../30-components/pipeline.md)
> Post 상태 전이 → [`docs/60-runtime/post-state-machine.md`](../60-runtime/post-state-machine.md)
