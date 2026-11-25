# 작업 결과: repo-reorg

## 1. 작업 결과

프로젝트 루트를 Docker 서비스 단위로 재구성 완료.

### 변경 전 (혼재된 루트 ~20개 항목)
```
WaggleBot/
├── ai_worker/   analytics/   crawlers/   dashboard/
├── dashboard_worker/   db/   monitoring/   uploaders/   test/
├── main.py   scheduler.py
├── backend/   frontend/   llm-worker/   claude-telegram-bridge/
├── config/   env/   scripts/   docs/
├── venv/   .venv/   __pycache__/   .idea/   NVIDIA Corporation/
└── media/   .result/   .streamlit/   ...
```

### 변경 후 (Docker 단위별 ~10개 항목)
```
WaggleBot/
├── worker/          ← ⭐ NEW: Python 모놀리스 (4 서비스 공유)
│   ├── ai_worker/  analytics/  crawlers/  dashboard/
│   ├── dashboard_worker/  db/  monitoring/  uploaders/  test/
│   ├── main.py  scheduler.py
│   ├── requirements.txt  Dockerfile
├── backend/         ← Spring Boot (변경 없음)
├── frontend/        ← Next.js (변경 없음)
├── llm-worker/      ← LLM 게이트웨이 (변경 없음)
├── claude-telegram-bridge/   (변경 없음)
├── config/          ← 루트 공유 (worker + backend 공통)
├── scripts/         ← ops 유틸 (루트 유지)
├── env/             ← docker-compose.yml, .env, Dockerfile.comfyui
└── docs/            ← 문서 (untracked)
```

---

## 2. 수정 내용

### 파일 이동 (physical mv, git rename detection 예정)
| 원래 위치 | 새 위치 | 비고 |
|---|---|---|
| `ai_worker/`, `analytics/`, `crawlers/`, `dashboard/`, `dashboard_worker/`, `db/`, `monitoring/`, `uploaders/`, `test/` | `worker/` 아래 | Python 패키지 일괄 이동 |
| `main.py`, `scheduler.py` | `worker/main.py`, `worker/scheduler.py` | Docker CMD 진입점 |
| `env/Dockerfile` | `worker/Dockerfile` | Python 빌드용 이미지 |
| `env/requirements.txt` | `worker/requirements.txt` | 의존성 목록 |

### 삭제된 항목
- `venv/`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `.idea/` — untracked 잡파일
- `NVIDIA Corporation/` — 비정상 생성 디렉토리
- `media/` — 빈 untracked 런타임 디렉토리 (Docker bind mount로 재생성)
- `.result/` — 불필요한 샘플 디렉토리 (tracked 1개 파일 포함 → git D 상태)
- `.streamlit/` — Streamlit 레거시 설정 (Next.js로 전환 완료)

### `worker/Dockerfile` 수정
```diff
- COPY env/requirements.txt .
+ COPY worker/requirements.txt .
- COPY . .
+ COPY worker/ ./
+ COPY config/ ./config/
```
빌드 컨텍스트는 repo 루트(`..`) 유지 → `config/`를 함께 COPY.

### `env/docker-compose.yml` 수정
- **4개 Python 서비스** (`crawler`, `ai_worker`, `monitoring`, `dashboard_worker`):
  - `dockerfile: env/Dockerfile` → `dockerfile: worker/Dockerfile`
  - 볼륨 `../:/app` → `../worker:/app`
  - 볼륨 `../config:/app/config` 추가
- **`ai_worker`**: `../assets:/app/assets` 추가 (BGM/폰트 마운트)
- **`comfyui`**: `../ai_worker/video/workflows` → `../worker/ai_worker/video/workflows`

### `.gitignore` 수정
- `media/*` → `media/` (폴더 전체 ignore)
- `test/test_*` → `worker/test/test_*` (경로 갱신)
- `_request/`, `.result` 라인 제거
- `worker/.venv/` 추가

### `.dockerignore` 수정
- `worker/.venv/`, `worker/__pycache__/`, `worker/venv/` 추가

### `scripts/` sys.path 보정
- `scripts/fix_dc_images.py`: `sys.path.insert(0, str(_PROJECT_ROOT / "worker"))` 추가
- `scripts/tiktok_upload_test.py`: 동일

### `CLAUDE.md` + `README.md`
- 모듈 구조 표 경로 `ai_worker/` → `worker/ai_worker/` 등 전체 업데이트
- README 프로젝트 트리 다이어그램 재구성

---

## 3. 테스트 결과물 저장 위치

해당 없음 (구조 재배치 작업).

---

## 4. 수동 테스트 방법

### 구조 확인
```bash
ls -1   # 루트에 ~10개 항목만
ls worker/  # 패키지들 + Dockerfile + requirements.txt
```

### git 커밋 (사용자가 직접)
```bash
# 이동을 git에 반영 (rename detection 자동)
git add -A
git status  # Renamed: ai_worker/ -> worker/ai_worker/ 등으로 나타나야 함
```

### Docker 빌드 테스트
```bash
cd env
docker compose build crawler ai_worker monitoring dashboard_worker
```

### 런타임 스모크 테스트
```bash
cd env
docker compose up db llm-worker ai_worker
docker compose logs --tail 50 ai_worker  # config/layout.json 로드 성공 확인
```

### Python import 검증 (worker 내부)
```bash
cd worker
PYTHONPATH=..:. python -c "from ai_worker.core.main import *; from db.models import Post; print('OK')"
```

---

## 5. 추천 commit message

```
refactor: docker 단위 기준 루트 구조 재정리 (worker/ 분리)

- Python 모놀리스 12개 패키지를 worker/ 로 통합
  (crawler/ai_worker/monitoring/dashboard_worker 4개 서비스 공유)
- env/Dockerfile + requirements.txt → worker/ 이동
- config/ 루트 유지 (backend-Python 공유 리소스)
- 잡파일/레거시 디렉토리 정리 (venv, .idea, .streamlit, media 등)
- docker-compose.yml: worker/Dockerfile, ../worker:/app, assets 마운트 반영
```
