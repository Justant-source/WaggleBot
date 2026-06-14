# 크롤러 품질 정상화

## 1. 작업 결과

| 항목 | 이전 | 이후 |
|------|------|------|
| 사이트당 수집 개수 | 무제한 (수백 건) | 상위 20건으로 제한 |
| theqoo 공지 수집 | 공지 6개 포함 (engagement_score 9568까지) | `tr.notice` 행 제외, 실제 인기글 20개만 |
| mlbpark 출처 | `?b=bullpen` 일반 게시판 (순차 잡글, likes=0 대부분) | `mp/best.php` TODAY BEST (실제 인기글, likes 실제값) |
| instiz 추천수 | 항상 0 | `b[class^="votenow"]` pre-render 파싱 (best-effort) |
| 오염 데이터 정리 | — | mlbpark 48건 + 공지 6건 DECLINED |

## 2. 수정 내용

### `config/crawler.py`
- `MAX_POSTS_PER_SITE = int(os.getenv("MAX_POSTS_PER_SITE", "20"))` 추가

### `config/settings.py`
- `MAX_POSTS_PER_SITE` re-export 추가

### `worker/crawlers/base.py`
- `run()` 내 `fetch_listing()` 반환 후 `listings[:MAX_POSTS_PER_SITE]`로 상한 적용
- 7개 크롤러 모두 중앙 제어

### `worker/crawlers/theqoo.py`
- `fetch_listing()` — `soup.find_all("a")` 방식 → `table tbody tr` 행 기반 순회로 변경
- `tr.notice` 클래스 포함 행 건너뜀 → 공지 완전 제외

### `worker/crawlers/mlbpark.py`
- `SECTIONS` → `mp/best.php` (TODAY BEST) 단일 섹션으로 교체
- `parse_post()` 변경 없음 (셀렉터 호환 확인)

### `worker/crawlers/instiz.py`
- `parse_post()` 내 `.fan-option-button-group` decompose **이전에** `b[class^="votenow"]` 파싱
- `likes = 0` 하드코딩 제거 → 실제값 또는 0 (best-effort)
- 댓글수: `#nowsubject .cmt` 읽기를 decompose 이전으로 이동 (이전 작업에서 수정 완료)

### DB 정리 (1회성)
```sql
-- mlbpark 구 bullpen 잡글 48건 DECLINED
UPDATE posts SET status='DECLINED' WHERE site_code='mlbpark' AND status='COLLECTED';
-- 공지 패턴 6건 DECLINED
UPDATE posts SET status='DECLINED' WHERE status='COLLECTED' AND title LIKE '%공지%' ...;
```

## 3. 테스트 결과물 위치

검증 명령 실행 결과 (2026-06-14):

```
=== mlbpark ===
listing: 25 posts
first: '재매이 찍고 인생 망한 그 사이트 사람들 ㅋㅋ'
stats: {'views': 16091, 'likes': 169, 'comments_count': 155}   ← likes 실제값!

=== theqoo ===
listing: 20 posts (공지 제외)
first: '멕시코 사람이 인종차별했음에도...'
stats: {'views': 6345, 'likes': 0, 'comments_count': 69}       ← 공지 0개, 댓글 채워짐

=== instiz ===
listing: 47 posts → base.py가 20건으로 제한
first: '미국인들이 느끼는 한국 감자튀김 불만'
stats: {'views': 77047, 'likes': 1, 'comments_count': 160}     ← votenow 파싱 성공

nate_pann: 50건 → 상위 20건으로 제한 (scheduler 로그 확인)
```

## 4. 수동 테스트 방법

```bash
# 크롤러 로그 확인
docker compose -f env/docker-compose.yml logs --tail 50 crawler

# 개별 크롤러 즉시 테스트
docker compose -f env/docker-compose.yml exec crawler python3 -c "
import sys; sys.path.insert(0,'/app')
import logging; logging.basicConfig(level=logging.WARNING)
from crawlers.mlbpark import MlbparkCrawler
c = MlbparkCrawler(); ls = c.fetch_listing()
print('mlbpark listing:', len(ls), 'posts')
d = c.parse_post(ls[0]['url']); print('stats:', d['stats'])
"

# DB 통계 확인
docker compose -f env/docker-compose.yml exec db mariadb -u wagglebot -pwagglebot wagglebot -e "
SELECT site_code,
       COUNT(*) as cnt,
       ROUND(AVG(CAST(JSON_VALUE(stats,'\$.likes') AS DECIMAL)),1) as avg_likes,
       ROUND(AVG(CAST(JSON_VALUE(stats,'\$.comments_count') AS DECIMAL)),1) as avg_cmt
FROM posts WHERE status='COLLECTED' GROUP BY site_code;
"

# 화면 확인: http://100.115.252.61:3000/admin/inbox
```

## 5. 추천 commit message

```
fix: 크롤러 품질 정상화 — 상위 20개 제한, 공지 제외, mlbpark TODAY BEST 전환, instiz 추천 파싱
```

## 6. 갱신한 문서

없음 (코드+설정 변경만, docs/ 기술 사실 변경 없음)

---

## 알려진 한계

- **instiz 추천수**: 정적 HTML에 일부만 pre-render → 부분 커버리지 (완전 수집은 JS 렌더링 필요)
- **theqoo 추천수**: 사이트에 기능 없음 → likes=0 정상
- `MAX_POSTS_PER_SITE` 기본값 20 — `.env`에서 `MAX_POSTS_PER_SITE=N`으로 조정 가능
