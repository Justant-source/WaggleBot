# 크롤러 수집 문제 수정

## 1. 작업 결과
네이트판 외 크롤러가 실행되지 않던 문제를 수정했습니다.

**원인:** `docker-compose.yml` crawler 서비스의 `environment` 섹션에 `ENABLED_CRAWLERS`가 누락되어 있었습니다.
- `.env`에 `ENABLED_CRAWLERS=nate_pann,bobaedream,dcinside,fmkorea`로 설정되어 있었지만
- Docker 컨테이너에 주입되지 않아 `config/crawler.py:13` 기본값인 `"nate_pann"`만 사용됨

## 2. 수정 내용

### `env/docker-compose.yml`
```yaml
# crawler 서비스 environment에 추가
ENABLED_CRAWLERS: ${ENABLED_CRAWLERS:-nate_pann}
```

### `env/.env.example`
```
# 크롤러 섹션에 추가
ENABLED_CRAWLERS=nate_pann,bobaedream,dcinside,fmkorea
```

## 3. 테스트 결과물 위치
없음 (컨테이너 미실행 환경)

## 4. 수동 테스트 방법
```bash
# 컨테이너 재시작
docker compose -f env/docker-compose.yml up -d crawler

# 로그에서 활성 크롤러 목록 확인
docker compose -f env/docker-compose.yml logs --tail 30 crawler
# "Enabled crawlers: ['nate_pann', 'bobaedream', 'dcinside', 'fmkorea']" 출력 확인

# instiz·theqoo·mlbpark도 활성화하려면 .env 수정
# ENABLED_CRAWLERS=nate_pann,bobaedream,dcinside,fmkorea,instiz,theqoo,mlbpark
```

## 5. 추천 commit message
```
fix: ENABLED_CRAWLERS env var docker-compose crawler 서비스에 주입 누락 수정

env/.env에 설정된 값이 컨테이너에 전달되지 않아
nate_pann 기본값만 동작하던 문제 해결.
.env.example에도 ENABLED_CRAWLERS 항목 추가.
```

## 6. 갱신한 문서 목록
없음 (설정 파일 수정만)
