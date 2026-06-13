# dcinside-imgfix

## 1. 작업 결과

`worker/crawlers/dcinside.py`의 `parse_post()` 내 본문 추출 로직을 개선하여 이미지 위주 게시글에서 `[원본 보기]` (7자)만 반환되던 문제를 해결했다.

## 2. 수정 내용

**파일:** `worker/crawlers/dcinside.py` (lines 133~157)

변경 전:
```python
content = body_el.get_text("\n", strip=True) if body_el else ""
content = re.sub(r"출처\s*:.*?(?:\[원본\s*보기\])?$", "", content, flags=re.MULTILINE).strip()
```

변경 후 (3단계):
1. **출처 라인 전체 제거**: `re.sub(r"출처\s*:.*", ...)` — `출처:` 이후 모든 내용(갤러리명 + `[원본 보기]` 링크 텍스트)을 한 번에 제거
2. **단독 `[원본 보기]` 라인 제거**: `re.sub(r"^\[원본\s*보기\]\s*$", ...)` — 출처가 없는 글에서 `[원본 보기]`가 단독 줄로 남는 경우 추가 처리
3. **이미지 위주 글 content 보완**: `img[data-fileno]`로 실제 DC 업로드 이미지 수 카운트 → content가 20자 미만이고 이미지가 있으면 `[이미지 N장]` 형태로 content 생성. alt 텍스트가 의미있으면(길이 < 50, 비-hex) 캡션으로 추가.

**원인 분석:**
- DC의 출처 구조: `<b>출처: XXX <a>[원본 보기]</a></b>` — `get_text()`로 평탄화 시 `"출처: XXX [원본 보기]"` 한 줄이 됨
- 기존 regex `출처\s*:.*?(?:\[원본\s*보기\])?$`의 `.*?` (non-greedy)가 `[원본` 앞에서 멈춰 링크 텍스트가 잔존

## 3. 테스트 결과

| URL | title | content (전) | content (후) |
|-----|-------|-------------|-------------|
| dcbest#436733 (이미지 14장) | 14pic) 못찍었음 청년 | `[원본 보기]` (7자) | `[이미지 14장]` (9자) |
| dcbest#436700 (이미지 50장+텍스트) | [ㅇㅎ] 이치노세 루나... | `[시리즈] 1\n...\n[원본 보기]` | `[시리즈] 1\n· 이치노세 루나 ...` (28자) |

## 4. 수동 테스트 방법

```bash
docker exec env-ai_worker-1 bash -c "cd /app && PYTHONPATH=/app python -c \"
from crawlers.dcinside import DcInsideCrawler
c = DcInsideCrawler()
r = c.parse_post('https://gall.dcinside.com/board/view/?id=dcbest&no=436733&_dcbest=1&page=1')
print('content:', repr(r['content']))
print('images:', len(r['images'] or []))
\""
```

## 5. 추천 commit message

```
fix: DC인사이드 이미지 위주 글 본문 [원본 보기] 잔존 문제 수정

- 출처 regex를 non-greedy→greedy로 변경해 링크 텍스트까지 제거
- 단독 [원본 보기] 라인 추가 제거 regex 적용
- content < 20자이고 data-fileno 이미지가 있으면 [이미지 N장] 보완 로직 추가
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 (크롤러 버그 픽스, 구조 변경 없음)
