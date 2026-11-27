#!/usr/bin/env python3
"""WaggleBot 발음 프로필(``config/tts_profile/*.yaml``)을 Local-TTS 서버에 올린다.

    python worker/tools/sync_tts_profile.py --dry-run     # 로컬 문서 확인 + 서버 :validate(저장 안 함). 업로드 없음
    python worker/tools/sync_tts_profile.py               # draft 업로드 -> 버전 :validate -> :preview(미리보기)
    python worker/tools/sync_tts_profile.py --activate    # 위 + 검증 통과 시 활성화(운영 반영은 명시 요청 시에만)

같은 문서를 다시 올리면 서버가 기존 버전을 돌려준다(새 버전 없음). 프로필 키는 ``wagglebot/<name>`` 이고
``X-Client-Id`` 도 ``wagglebot`` 이어야 한다. 실행은 저장소 루트에서: ``PYTHONPATH=.:worker``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "worker"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import yaml  # noqa: E402

from ai_worker.tts.local_tts_client import LocalTTSError, LocalTTS  # noqa: E402
from config.settings import TTS_CLIENT_ID, TTS_SERVER_TOKEN  # noqa: E402

DEFAULT_FILE = ROOT / "config" / "tts_profile" / "shorts-ko.yaml"
DEFAULT_URL = "http://127.0.0.1:8500"   # 호스트에서 실행하는 기본값(컨테이너 안에서는 --url http://local-tts:8500)
PREVIEW_SAMPLES = [
    "남친과 헤어졌어", "AI가 CCTV를 봤다", "5G 요금제 5GB", "3.5초 걸렸다 6월 10월", "장모님이 베댓을 봤다",
]


def _fail(msg: str) -> int:
    print(f"[오류] {msg}", file=sys.stderr)
    return 1


def _print_report(rep: dict) -> None:
    t = rep.get("tests", {})
    print(f"  ok={rep.get('ok')} errors={len(rep.get('errors', []))} warnings={len(rep.get('warnings', []))} "
          f"tests={t.get('passed')}/{t.get('total')} stats={rep.get('stats')}")
    for e in rep.get("errors", []):
        print(f"  - 오류 {e.get('code')}: {e.get('message')} ({e.get('path')})")
    for w in rep.get("warnings", []):
        print(f"  - 경고 {w.get('code')}: {w.get('message')}")
    for f in t.get("failed", []):
        print(f"  - 골든 실패: {f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", type=Path, default=DEFAULT_FILE, help="프로필 YAML (기본 config/tts_profile/shorts-ko.yaml)")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"Local-TTS 주소(기본 {DEFAULT_URL})")
    ap.add_argument("--dry-run", action="store_true", help="저장 없이 서버 :validate 만 수행")
    ap.add_argument("--activate", action="store_true", help="검증 통과 시 활성화")
    ap.add_argument("--force-warnings", action="store_true", help="활성화 시 경고 무시")
    args = ap.parse_args(argv)

    try:
        doc = yaml.safe_load(args.file.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        return _fail(f"프로필 파일 읽기 실패: {exc}")
    pid = doc.get("profile")
    if not pid or not pid.startswith(f"{TTS_CLIENT_ID}/"):
        return _fail(f"profile 은 '{TTS_CLIENT_ID}/<name>' 이어야 합니다: {pid!r}")
    print(f"파일 {args.file.relative_to(ROOT)}  profile={pid}  entries={len(doc.get('entries', []))} tests={len(doc.get('tests', []))}")

    try:
        with LocalTTS(args.url, client=TTS_CLIENT_ID, token=TTS_SERVER_TOKEN or None) as cli:
            if args.dry_run:
                rep = cli._json("POST", "/v1/profiles:validate", json=doc)
                print("서버 검증(저장 안 함):")
                _print_report(rep)
                return 0 if rep.get("ok") else 1

            ver = cli.upload_profile(pid, doc)
            n = ver["version"]
            print(f"업로드: v{n} state={ver.get('state')} sha256={ver.get('sha256')} doc_sha256={ver.get('doc_sha256')}")
            rep = cli.validate_profile(pid, n)
            print("검증:")
            _print_report(rep)

            prev = cli.preview_profile(pid, n, "\n".join(PREVIEW_SAMPLES), diff=False)
            for r in prev.get("results", []):
                print(f"  미리보기: {r.get('normalized')!r}")

            if not rep.get("ok"):
                return _fail("검증 실패 — 활성화하지 않음")
            if args.activate:
                cli.activate_profile(pid, n, force_warnings=args.force_warnings)
                now = cli.get_profile(pid)
                print("활성화:", json.dumps({k: now.get(k) for k in ("profile", "active", "active_sha256", "activated_at")}, ensure_ascii=False))
            else:
                print("draft 상태(활성화하려면 --activate)")
    except LocalTTSError as exc:
        return _fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
