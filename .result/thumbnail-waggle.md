# thumbnail-waggle — YouTube 썸네일 와글 브랜드 디자인 교체

## 1. 작업 결과

기존 dramatic/question/funny/news 그라데이션 스타일 썸네일을 **와글 브랜드 통일 디자인**으로 교체했다.
영상(쇼츠)와 썸네일의 브랜드 불일치 해소.

**와글 썸네일 레이아웃 (1280×720):**
- 노란 헤더 바 80px: `#FBD024`, 중앙 "와글" bold 40px, 좌← 우≡ 아이콘
- 좌측 55%(700px): 굵은 검정 훅 텍스트, 자동 줄수 조절(76→68→60→52px), 최대 3줄
- 우측 45%(580px): 게시글 이미지 fill-crop — 이미지 없을 때 노란 패널(100px 우측 밴드)
- 텍스트 아래 노란 액센트 바 (180×8px)
- 배경 흰색 `#FFFFFF`

기존 mood별 스타일 매핑(`_MOOD_TO_STYLE`) 삭제 — "waggle" 단일 스타일로 통일.

## 2. 수정 내용

| 파일 | 변경 내용 |
|------|----------|
| `worker/ai_worker/renderer/thumbnail.py` | `_generate_waggle()` 신규, `generate_thumbnail()` 기본값 "waggle"로 변경, "waggle" 분기 추가 |
| `worker/ai_worker/renderer/composer.py` | `compose_thumbnail()` 기본값 "dramatic" → "waggle" |
| `worker/ai_worker/core/processor.py` | inline 경로·render_stage 두 곳 `_MOOD_TO_STYLE` 제거, `style="waggle"` 직접 지정 |

## 3. 테스트 결과물 위치

컨테이너 테스트 JPEG 2개:
```
/tmp/wb_thumb_test/thumb_no_img.jpg    — 이미지 없음 (노란 우측 패널)
/tmp/wb_thumb_test/thumb_long_text.jpg — 긴 텍스트 자동 2줄 래핑
```

두 케이스 모두: 와글 헤더 정상, 텍스트 2줄 자동 래핑, 노란 액센트 바 확인.

## 4. 수동 테스트 방법

```bash
docker compose -f env/docker-compose.yml exec ai_worker python3 - <<'EOF'
from pathlib import Path
from ai_worker.renderer.thumbnail import generate_thumbnail

out = Path("/tmp/thumb_test"); out.mkdir(exist_ok=True)
generate_thumbnail("카톡 한 줄에 5년 사귄 남친이랑 헤어진 썰", [], out / "t1.jpg")
generate_thumbnail("직장 상사가 결혼식날 갑자기 나오라고 한 이유", [], out / "t2.jpg")
print("OK:", list(out.glob("*.jpg")))
EOF
```

```bash
# 결과 복사해서 확인
docker compose -f env/docker-compose.yml cp ai_worker:/tmp/thumb_test/t1.jpg /tmp/
```

## 5. 추천 commit message

```
feat: YouTube 썸네일 와글 브랜드 디자인 교체

dramatic/funny/news 그라데이션 → 흰배경+노란헤더+굵은검정텍스트.
_MOOD_TO_STYLE 제거, style="waggle" 단일 통일.
이미지 없으면 노란 우측 패널 폴백, 텍스트 자동 크기 조절(최대 3줄).
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 — thumbnail.py는 docs/ SSOT 범위에 별도 항목 없음.
`implementation-status.md` 갱신 권장.
