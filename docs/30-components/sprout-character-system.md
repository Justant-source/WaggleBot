# 시봄이(Sibom) 캐릭터 일러스트 시스템 — 참조

**상태**: 설계 진행중(1/2 배치, 30/60장). **런타임 미연동** — 아래 코드 경로는 아직 이 자산을 쓰지 않는다.
**권위본**: Again-Spring 레포 `docs/frontend/design/specs/sprout-character-system/README.md`
(결정 로그·캐릭터 바이블·슬롯 프리셋·`catalog.json` 스키마·Claude Design 프로젝트 정보 전부 그쪽에 있음. 여기는 포인터 + 이 레포에서 필요한 것만 요약)

---

## 이 레포에 있는 것

```
assets/sprouts_design/
├── gen.py            # SVG 생성기 (Again-Spring 레포와 동일본)
├── build_page.py      # Claude Design 리뷰 페이지 빌더
├── catalog.json        # 30장 메타데이터 (Again-Spring 레포와 동일본)
└── svg/                 # 30장 원본 SVG + 표정 세트 20종 (820×820, 배경 투명, 자체완결형)
```

**아직 안 한 것**: `svg/*.svg` → PNG 렌더, `assets/sprouts/*.png`로 배치(현재 `assets/metaphors/*.png`와 같은 급). 60장 확정 전까지는 `_design/` 접두로 보류 상태 유지.

---

## 이 자산이 최종적으로 붙을 자리 (계획 — 아직 미구현)

기존 `assets/metaphors/*.png`(60종 사물 은유)와 같은 패턴으로, `assets/sprouts/*.png` + `assets/sprouts/catalog.json`이 런타임 SSOT가 된다.

연동 예정 지점(변경 전):
- `worker/ai_worker/scene/director.py` — `_resolve_metaphor_image(s)`와 같은 패턴으로 `_resolve_sprout_image(s)` 추가 예정
- `worker/ai_worker/pipeline/content_processor.py` 부근의 본문 스크립트 LLM — 문단마다 `{image_id, caption}`을 `catalog.json`의 `trigger`+`keywords`를 컨텍스트로 받아 직접 선택하도록 프롬프트 확장 예정
- `again_spring` 전용 `distribute_images()`(균등분배) 경로를 이 명시적 매핑으로 교체 예정
- `config/layout.json`의 `image_text.elements.image_area`(x90 y550 w820 h820, 1:1 배율 확인됨) — 슬롯 좌표 유효성 재검증 필요

**이 자산을 실제로 배선하는 작업(위 4개)은 사용자의 명시적 지시 없이 시작하지 말 것** — Again-Spring 쪽 README §6.2/§7에도 동일하게 명시돼 있다.

---

## 도메인 이름과의 관계

`config/settings.py`의 `site_code == "again_spring"` 분기(Tone L 테마 등)와 함께 동작할 자산이다. 다른 사이트(와글 등)에는 적용 대상 아님.
