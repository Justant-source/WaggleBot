# WaggleBot — 시스템 아키텍처

> **last-verified:** 2026-06-11 (commit `3ba0d15`)
> **scope:** 시스템 구조, Post 상태 전이, VRAM 배분 — SSOT

커뮤니티 게시글을 자동으로 크롤링해 LLM 대본→TTS→비디오→업로드까지 처리하는 AI 컨텐츠 자동화 파이프라인.

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
        FISH[Fish Speech 1.5<br/>TTS :8082]
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

## 서비스 레이어 구조

```mermaid
graph LR
    subgraph Layer1["수집 레이어"]
        C[crawler]
    end
    subgraph Layer2["API 레이어"]
        B[backend<br/>Spring Boot]
        F[frontend<br/>Next.js]
    end
    subgraph Layer3["처리 레이어"]
        A[ai_worker]
        D[dashboard_worker]
    end
    subgraph Layer4["AI 서비스"]
        L[llm-worker]
        FS[fish-speech]
        CUI[comfyui]
    end
    subgraph Layer5["영속성"]
        DB[(MariaDB)]
        MEDIA[/media 볼륨/]
    end

    Layer1 --> Layer5
    Layer2 <--> Layer5
    Layer3 --> Layer4
    Layer3 <--> Layer5
    Layer4 --> Layer5
    F <--> B
```

## Post 상태 전이

```mermaid
stateDiagram-v2
    [*] --> COLLECTED : 크롤러 수집
    COLLECTED --> EDITING : 수동/자동 편집 시작
    EDITING --> APPROVED : 승인
    EDITING --> COLLECTED : 편집 취소
    APPROVED --> PROCESSING : ai_worker 처리 시작
    PROCESSING --> PREVIEW_RENDERED : 8-Phase 완료
    PREVIEW_RENDERED --> RENDERED : 최종 렌더링 완료
    PREVIEW_RENDERED --> DECLINED : 거절
    RENDERED --> UPLOADED : YouTube 업로드 완료
    RENDERED --> FAILED : 업로드 실패
    PROCESSING --> FAILED : 파이프라인 실패 (last_error 저장)
    FAILED --> APPROVED : 재시도 (retryCount++, last_error 초기화)
```

## GPU VRAM 배분 (RTX 3090 24GB)

```mermaid
pie title VRAM 사용 배분 (~17.7GB / 24GB)
    "LTX-2 distilled GGUF Q4 UNet" : 12.7
    "Fish Speech TTS" : 5.0
    "안전 마진" : 6.3
```

> Gemma-3-12B 텍스트 인코더(~15GB)는 `--lowvram` 플래그로 CPU에서 실행 (VRAM 미사용).

## 기술 스택 요약

| 영역 | 기술 |
|------|------|
| **크롤러** | Python 3.12, aiohttp, BeautifulSoup |
| **백엔드** | Java 21, Spring Boot 3.3, MariaDB 11, Flyway |
| **프론트엔드** | Next.js 14 (App Router), TypeScript |
| **LLM 게이트웨이** | Java 21, Spring Boot 3.3, Claude CLI subprocess |
| **LLM** | Claude haiku-4-5 / sonnet-4-6 — CLI 백엔드(구독) 또는 API 백엔드(`ANTHROPIC_API_KEY`) |
| **TTS** | Fish Speech v1.5.1 (zero-shot 클로닝) |
| **비디오** | ComfyUI + LTX-2 19B distilled GGUF Q4 (8-step) |
| **렌더링** | FFmpeg (h264_nvenc) |
| **컨테이너** | Docker Compose, NVIDIA Container Runtime |
| **DB** | MariaDB 11, SQLAlchemy (Python), JPA/Hibernate (Java) |
