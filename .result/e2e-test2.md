# e2e-test2

## 1. 작업 결과

post_id=193 (잠실 석촌 땅굴 발견, nate_pann) 풀 파이프라인 E2E 테스트 통과.

## 2. 테스트 환경

| 항목 | 상태 |
|------|------|
| 모든 Docker 서비스 | Healthy (11개) |
| LLM 백엔드 | `api` (Anthropic 직접) |
| `use_content_processor` | `true` (8-Phase 파이프라인) |
| VIDEO_GEN_ENABLED | true (ComfyUI LTX-2) |

## 3. 파이프라인 단계별 결과

| Phase | 내용 | 결과 |
|-------|------|------|
| Phase 1 | analyze_resources | ✓ 전략=text_heavy 이미지=1 |
| Phase 2 | chunk_with_llm (haiku) | ✓ hook=19자 body=8문장 closer=13자 (7.4초) |
| Phase 3 | validate_and_fix | ✓ mood=controversy |
| Phase 4 | SceneDirector (rule_based) | ✓ 씬=10개 |
| Phase 5 | TTS (Fish Speech) | ✓ 10프레임 23.6s (워밍업 스킵: 2.3h 캐시) |
| Phase 6 | video_prompt (병렬) | ✓ asyncio.gather |
| Phase 7 | ComfyUI LTX-2 (T2V Distilled) | ✓ 씬 2,5,7,9 클립 생성 |
| Phase 8 | FFmpeg h264_nvenc 렌더링 | ✓ 23.6s 완료 |

## 4. 결과물 검증

- **파일:** `/app/media/video/nate_pann/post_375457820_SD.mp4` (7.3MB)
- **코덱:** h264 (h264_nvenc) ✓
- **해상도:** 1080×1920 (9:16 세로) ✓
- **길이:** 23.5s ✓
- **fps:** 30 ✓
- **상태:** `PREVIEW_RENDERED` ✓
- **썸네일:** `/app/media/thumbnails/nate_pann/post_375457820.jpg` ✓

## 5. 개선 사항 검증 (이번 세션 수정 포함)

| 수정 사항 | 확인 |
|----------|------|
| `use_content_processor` fresh config 읽기 | ✓ "content_processor 모드: 전략=text_heavy" 로그 확인 |
| Fish Speech 워밍업 스킵 (WP-6) | ✓ "워밍업 스킵 (캐시 유효, 2.3h 전 웜업)" |
| Phase 5∥6 병렬 (WP-5) | ✓ asyncio.gather TTS+video_prompt 동시 실행 |
| Phase 7 ComfyUI T2V Distilled | ✓ 씬 4개 생성 (steps=8, cfg=1.0) |
| h264_nvenc 단일 패스 (WP-3) | ✓ intermediate 재인코딩 없음 |

## 6. 알려진 한계 (버그 아님)

- Fish Speech 참조 오디오 미배포 → 기본 음성 폴백 (voice_preview_yohan.mp3)
- JSON 파싱 첫 시도 실패 → 정규식 폴백으로 자동 복구 (무해)

## 7. 추천 commit message

해당 없음 (코드 변경 없는 테스트만 수행)

## 8. DOC-MAP 기준 갱신한 문서 목록

없음
