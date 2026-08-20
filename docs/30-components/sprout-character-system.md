# 시봄이(Sibom) 캐릭터 일러스트 시스템 — 참조

**상태**: 구현 완료(2026-08-21). **런타임 연동** — 렌더 파이프라인 Phase 8(FFmpeg)에서 시봄이 캐릭터 모션 완전 동작중. 아래는 설계 아카이브 + 현재 구현 위치.
**권위본**: Again-Spring 레포 `docs/frontend/design/specs/sprout-character-system/README.md`
(결정 로그·캐릭터 바이블·슬롯 프리셋·`catalog.json` 스키마·Claude Design 프로젝트 정보 전부 그쪽에 있음. 여기는 포인터 + 이 레포에서 필요한 것만 요약)

---

## 현재 구현 상태 (2026-08-21)

### 모션 시스템 (완전 동작)

`worker/ai_worker/renderer/layout.py`에서 시봄이 모션을 완전 구현:

- **`_sibom_variant(pil, scale, dx, dy, alpha)`** — 캐릭터를 자기 캔버스 안에서 변형(등장 punch + 루프). 미디어 박스 위치 가변성 처리로 `_frames.py` 수정 필수 없음.
- **`_sibom_motion_sequences(...)`** — 등장 punch(12프레임, ease-out scale 92→100 + 페이드) + dwell 루프(사인 기반 모션)
- **`_wire_sibom_motion(entry, render_frame, ...)`** — `intro`(start_alpha 0.60, 썸네일 후보) / `image_text`(0.35)에서 호출. 실패 시 정지 프레임으로 graceful degrade
- **모션 종류** — `assets/sprouts/catalog.json`의 각 이미지 `motion` 필드가 결정: `sway`(숨쉬기 ±3%) · `shake`(잔떨림) · `sob`(세로 들썩임) · `sink`(처짐) · `pop`(크게 숨쉬기)
- **루프 특성**: 사인 기반 → `i=0`·`i=n` 타일링 튐 방지. `sibom_dwell="punch"`는 루프 없이 등장만.
- **미구현**: 눈 깜빡임 — 감은 눈 PNG 자산 부재로 scale/offset 모션만 적용
- **검증**: `worker/test/test_sibom_motion.py`(유닛 18개) + `worker/test/smoke_sibom_motion.py`(실렌더 픽셀 검증, 컨테이너에서 `python3 /app/test/smoke_sibom_motion.py`)

### 캐릭터 아트 리파인 (2026-08-20)

- 눈 확대 + 하이라이트 추가
- 진영색을 캐릭터 전용 밝은 값(`#E89A72` 작성자 / `#6FB08A` 상대방)으로 변경
- 외곽선 7→9px, 팔다리 22→28px
- 떡잎 `bristle`(곤두섬) 신규 추가
- 자산: `assets/sprouts/`

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
