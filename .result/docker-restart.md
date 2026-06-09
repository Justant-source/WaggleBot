# Docker 전체 재구동 작업 결과

## 1. 작업 결과

모든 11개 WaggleBot Docker 서비스가 정상 실행됨.

| 서비스 | 상태 | 포트 |
|--------|------|------|
| env-db-1 | Up (healthy) | 3306 |
| llm-worker | Up (healthy) | 8090 |
| env-backend-1 | Up | 8080 |
| fish-speech | Up (healthy) | 8082 |
| comfyui | Up (healthy) | 8188 |
| env-ai_worker-1 | Up | — |
| env-crawler-1 | Up | — |
| env-dashboard_worker-1 | Up | — |
| env-monitoring-1 | Up | — |
| env-frontend-1 | Up | 3000 |
| telegram-bridge | Up | 3847 |

## 2. 수정 내용

### 2-1. `env/docker-compose.yml`
- fish-speech 포트 `8080:8080` → `8082:8080` (backend와 충돌 해소)

### 2-2. `env/Dockerfile.comfyui` (핵심 수정)
- **문제**: `nvidia/cuda:13.0.1-runtime-ubuntu22.04`의 기본 `python3.11` apt 패키지가
  `3.11.0~rc1` (릴리스 후보)로, `sys.get_int_max_str_digits`가 없어
  `torch._dynamo.polyfills.sys` 로드 시 `AttributeError` 발생
- **해결**: deadsnakes PPA로 Python 3.12.13(stable) 설치로 교체
  - `add-apt-repository ppa:deadsnakes/ppa`
  - `python3.11` → `python3.12`, `python3.12-venv`, `python3.12-dev`
  - `LD_LIBRARY_PATH` 경로 `python3.11` → `python3.12`
  - 모든 `pip` 호출을 `python3.12 -m pip`으로 명시

### 2-3. fish-speech 모델 다운로드
- **문제**: `checkpoints/fish-speech-1.5/` 디렉토리 없음
- **해결**: HuggingFace `fishaudio/fish-speech-1.5`에서 모델 파일 다운로드
  - `/home/justant/Data/WaggleBot/checkpoints/fish-speech-1.5/`에 저장
  - `config.json`, `model.pth` (1.22GB), `firefly-gan-vq-fsq-8x1024-21hz-generator.pth` (180MB),
    `special_tokens.json`, `tokenizer.tiktoken`

### 2-4. Spring Boot 관련 (이전 세션)
- `backend/gradlew` 및 `worker/llm/gradlew` — 표준 classpath 방식으로 수정
- `backend/gradle/wrapper/gradle-wrapper.jar` — Gradle 8.8 내장 jar로 교체
- `backend/src/main/java/.../PostRepository.java` — `JpaSpecificationExecutor` 추가
- `frontend/public/.gitkeep` — Dockerfile COPY 오류 해소
- `worker/llm/src/` — Spring Boot llm-worker 전체 소스 신규 생성
  - `LlmWorkerApplication.java`, `LlmController.java`, `ClaudeService.java`,
    `InvokeRequest.java`, `application.properties`

## 3. 추가 수정: ComfyUI-LTXVideo kornia 패치

### 문제
```
Cannot import ComfyUI-LTXVideo: cannot import name 'pad' from 'kornia.geometry.transform.pyramid'
```
kornia 0.8.3에서 `kornia.geometry.transform.pyramid.pad`가 제거됨.

### 해결
`custom_nodes/ComfyUI-LTXVideo/pyramid_blending.py` 수정:
- import 블록에서 `pad,` 제거
- `pad(image, ...)` → `F.pad(image, ...)` (2곳)
- `F`(`torch.nn.functional`)는 이미 임포트되어 있어 추가 임포트 불필요

`Dockerfile.comfyui`에 빌드 시 자동 패치 추가 (영구 적용):
```python
python3.12 -c "import re, pathlib; p = pathlib.Path('pyramid_blending.py'); ..."
```

## 4. 테스트 결과물 저장 위치

- comfyui 빌드 로그: `C:\Users\Justant\AppData\Local\Temp\claude\...\tasks\b1mo1tqmy.output`
- fish-speech 모델: `/home/justant/Data/WaggleBot/checkpoints/fish-speech-1.5/`

## 5. 수동 테스트 방법

```bash
# 전체 컨테이너 상태 확인
wsl -d Ubuntu-24.04 -- bash -c "DOCKER_HOST=tcp://127.0.0.1:2375 docker ps"

# 서비스별 헬스체크
curl http://localhost:8080/api/health      # backend
curl http://localhost:8090/healthz         # llm-worker
curl http://localhost:8082/               # fish-speech
curl http://localhost:8188/               # comfyui
curl http://localhost:3000/               # frontend

# ai_worker 로그 확인
wsl -d Ubuntu-24.04 -- bash -c "DOCKER_HOST=tcp://127.0.0.1:2375 docker logs env-ai_worker-1 --tail 30"
```

## 6. 추천 commit message

```
fix: docker 전체 재구동 - Python 3.12 교체 및 fish-speech 모델 추가

- Dockerfile.comfyui: python3.11(rc1) → python3.12(deadsnakes PPA)
  torch._dynamo sys.get_int_max_str_digits AttributeError 해소
- docker-compose.yml: fish-speech 포트 8080→8082 (backend 충돌 해소)
- checkpoints/fish-speech-1.5/ 모델 파일 추가 (HuggingFace 다운로드)
- backend/worker/llm gradlew + gradle-wrapper.jar 수정
- llm-worker Spring Boot 소스 신규 생성 (POST /v1/invoke)
```
