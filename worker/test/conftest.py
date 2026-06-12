# 직접 실행용 통합 스크립트 — pytest 자동 수집 제외.
# test_pipeline_phases.py: 모듈 레벨 DB 접근 + sys.exit(1).
# test_fish_speech.py: async def test_*() 함수를 asyncio.run(main())으로 호출하는 구조 —
#   pytest-asyncio 없이 수집하면 "async def" PytestUnraisableExceptionWarning / 실패.
collect_ignore = [
    "test_pipeline_phases.py",
    "test_fish_speech.py",
]
