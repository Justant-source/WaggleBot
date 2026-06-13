# youtube-capture — 쇼츠 다운로드 + 주요 장면 캡쳐 (임시 격리 도구)

## 1. 작업 결과

`youtube/` 디렉토리 안에서만 동작하는 임시 도구를 신설. YouTube URL을 받아
영상을 다운로드하고 **컷(장면 전환)을 감지**해 장면별 대표 프레임을 저장한 뒤
**마크다운 리포트**를 생성한다. 시스템(ffmpeg/yt-dlp)을 건드리지 않고
`youtube/.venv` 안에 모든 의존성을 격리 설치.

**대상 15개 쇼츠 전부 처리 완료** — 다운로드 15/15, 리포트 15/15, 장면 프레임 총 **169장**.
모든 산출물은 `youtube/` 하위에만 생성됨(외부 유출 없음).

| 채널 | 영상 | 장면 수 |
|------|------|--------|
| 짤감자 | 당근 매너온도 70도 인성 ㄷㄷ | 13 |
| 짤감자 | 모르는 곳에서 카드 결제됐을 때 해결법 | 11 |
| 짤감자 | 암 환자 커플의 최후 | 10 |
| 짤감자 | 구질구질한 당근마켓 진상부모 | 16 |
| 짤감자 | 엉교육 시간에 절대 안 알려주는 것 | 18 |
| 썰레몬 | 배나온 여자친구 | 12 |
| 썰레몬 | 전설의 일진녀 | 21 |
| 썰레몬 | 수리센터에 갔다가 | 23 |
| 썰레몬 | 좋은 경험이었다 | 5 |
| 썰레몬 | 누나의 별명 | 8 |
| 심심한 회사원 | 진정한 어른의 플렉스 ㅋㅋㅋㅋ | 8 |
| 심심한 회사원 | 낚시하다 이상한걸 잡은 사람들 ㅋㅋㅋㅋ | 8 |
| 심심한 회사원 | 사장님을 웃게 만드는 배민 리뷰 ㅋㅋㅋㅋ | 5 |
| 심심한 회사원 | 나라가 인정한 공익 사유 레전드 ㅋㅋㅋㅋ | 3 |
| 심심한 회사원 | 어질어질한 자취방 대참사 레전드 ㅋㅋㅋㅋ | 8 |

## 2. 수정 내용

신규 파일 (전부 `youtube/` 하위):
- `youtube/capture.py` — 메인. 다운로드(yt-dlp) → 컷 감지(PySceneDetect ContentDetector) →
  장면 중간 프레임 추출(번들 ffmpeg) → 리포트 생성. `BASE` 하위 경로만 허용하는 격리 가드 포함.
- `youtube/setup.sh` — `.venv` 생성 + 의존성 설치(idempotent).
- `youtube/requirements.txt` — `yt-dlp`, `imageio-ffmpeg`(ffmpeg 바이너리 번들), `scenedetect[opencv]`.
- `youtube/urls.txt` — 대상 15개 URL(채널별 주석).
- `youtube/README.md` — 사용법.

기존 파일 수정:
- `.gitignore` — `youtube/.venv/`, `youtube/downloads/`, `youtube/output/` 추적 제외(소스만 추적).

핵심 트러블슈팅: YouTube 기본 제공 포맷이 **AV1**이라 opencv 장면감지가 소프트웨어
디코드에 실패(→ 1장면 폴백). yt-dlp `format`을 **H.264(avc1) 우선**으로 지정해 해결
(예: 5vbs4Z_NuaY 1장면 → 13장면 정상 감지).

## 3. 테스트 결과물 위치

- 프레임: `youtube/output/<id>__<title>/frames/scene-NNN.jpg` (총 169장)
- 리포트: `youtube/output/<id>__<title>/report.md` (15개, 제목·채널·길이·해상도 + 장면 타임스탬프 테이블 + 썸네일 임베드)
- 원본 영상: `youtube/downloads/<id>.mp4` (15개)
- 시각 검증 완료: scene-007.jpg 등 실제 영상 프레임 정상 렌더 확인(가비지 아님).

## 4. 수동 테스트 방법

```bash
cd youtube
bash setup.sh                                    # 최초 1회 (격리 venv 설치)

# 단일
.venv/bin/python capture.py https://www.youtube.com/shorts/5vbs4Z_NuaY
# 일괄 (15개)
.venv/bin/python capture.py --from urls.txt
# 컷 감지 튜닝 (임계값↓ = 더 많은 장면)
.venv/bin/python capture.py --from urls.txt --threshold 27 --min-scene-len 0.6
```
결과 확인: `youtube/output/<id>__*/report.md` 를 마크다운 뷰어로 열면 장면별 썸네일이 보인다.

## 5. 추천 commit message

```
feat(youtube): 쇼츠 다운로드+컷 감지 장면 캡쳐 임시 격리 도구 추가

youtube/ 안에서만 동작(시스템 미변경, .venv 격리). yt-dlp 다운로드 →
PySceneDetect 컷 감지 → 번들 ffmpeg 프레임 추출 → md 리포트.
AV1 대신 H.264 우선 다운로드로 opencv 장면감지 정상화. 대상 15개 처리 완료.
```

## 6. DOC-MAP 기준 갱신한 문서 목록

없음 — `youtube/`는 메인 파이프라인과 분리된 임시 격리 도구로, `docs/` SSOT 범위 밖.
사용법은 `youtube/README.md`에 자체 문서화.
