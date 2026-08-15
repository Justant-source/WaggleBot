import asyncio
from pathlib import Path
from ai_worker.tts.fish_client import synthesize

NARRATION = "이번 사연은 신혼집 인테리어를 두고 벌어진 다툼입니다. 벽지 색깔 하나로 시작된 대화가, 결국 서로의 가치관 차이로 번지고 말았습니다."
COMMENT = "와, 저라면 진짜 서운했을 것 같아요. 그래도 대화로 풀 수 있는 문제 같은데, 두 분 다 조금만 양보해 보시면 어떨까요?"

async def main():
    out_dir = Path("/app/assets/media/tmp/tts_listen_compare")
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("manbo", NARRATION, "manbo_fixed_narration.wav"),
        ("manu", NARRATION, "manu_fixed_narration.wav"),
        ("yura", NARRATION, "yura_fixed_narration.wav"),
        ("host_m", NARRATION, "host_m_narration.wav"),
        ("host_f", NARRATION, "host_f_narration.wav"),
        ("manbo", COMMENT, "manbo_fixed_comment.wav"),
        ("manu", COMMENT, "manu_fixed_comment.wav"),
        ("yura", COMMENT, "yura_fixed_comment.wav"),
        ("host_m", COMMENT, "host_m_comment.wav"),
        ("host_f", COMMENT, "host_f_comment.wav"),
    ]
    results = []
    for i, (voice, text, fname) in enumerate(jobs, 1):
        try:
            path = await synthesize(text, scene_type="compare", voice_key=voice, output_path=out_dir / fname)
            print(f"[{i}/10] OK {fname}")
            results.append(("OK", fname))
        except Exception as exc:
            print(f"[{i}/10] FAIL {fname}: {type(exc).__name__}: {exc}")
            results.append(("FAIL", fname))
    
    print("\n=== SUMMARY ===")
    ok_count = sum(1 for r, _ in results if r == "OK")
    print(f"Success: {ok_count}/10")

asyncio.run(main())
