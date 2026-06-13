# 직접 실행용 통합 스크립트 — pytest 자동 수집 제외.
# test_pipeline_phases.py: 모듈 레벨 DB 접근 + sys.exit(1).
# test_fish_speech.py: async def test_*() 함수를 asyncio.run(main())으로 호출하는 구조 —
#   pytest-asyncio 없이 수집하면 "async def" PytestUnraisableExceptionWarning / 실패.
# test_dc_images.py: def test_*() → bool 반환, DCInside 라이브 네트워크 요청 포함 —
#   pytest 수집 시 실행되어 외부 HTTP 요청 발생 (직접 실행: python -m test.test_dc_images).
# test_scene_director_dc_download.py: 동일 패턴, scene_director DC 이미지 다운로드 E2E.
collect_ignore = [
    "test_pipeline_phases.py",
    "test_fish_speech.py",
    "test_dc_images.py",
    "test_scene_director_dc_download.py",
    "test_render_progressive_mp4.py",
]
