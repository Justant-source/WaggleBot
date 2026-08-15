#!/usr/bin/env python3
"""타입캐스트 API 코퍼스 수집기 — 크레딧 안전장치 내장.

핵심 안전 설계:
  1. 재개형 장부(ledger.jsonl): 성공한 청크는 절대 재호출하지 않는다.
  2. 예산 가드: --budget-chars 초과 직전에 멈춘다(청크 단위, 초과 안 함).
  3. 실패/애매한 응답은 자동 재시도하지 않는다 — 사람이 로그 보고 판단.
  4. --dry-run: 실제 호출 없이 무엇을 얼마나 쓸지만 출력.

사용법:
  python3 _typecast_collect.py --voice-id tc_632293f759d649937b97f323 \
    --speaker-name JINWOO --corpus data-finetune-plan/corpus_chunks.json \
    --data-dir data-finetune --budget-chars 4000 [--dry-run]
"""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.typecast.ai/v1/text-to-speech"
SEED = 42  # 고정 시드 — 재현성 (plan2.md §5)
REQUEST_INTERVAL_SEC = 0.4


def load_api_key(path: str) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8").strip()


def load_ledger(ledger_path: Path) -> dict[int, dict]:
    """chunk_index -> 최신 레코드. 이미 success인 청크를 스킵하기 위함."""
    records: dict[int, dict] = {}
    if not ledger_path.exists():
        return records
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        records[rec["chunk_index"]] = rec
    return records


def append_ledger(ledger_path: Path, record: dict) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def call_typecast(api_key: str, voice_id: str, text: str, prev_text: str, next_text: str):
    """Typecast /v1/text-to-speech 호출. (status_code, body_bytes_or_error_json) 반환.

    urlopen이 예외를 던지지 않고 응답을 받았다면 과금이 확정된 것으로 간주한다
    (200이든 4xx든). 연결 자체가 실패한 경우만 "과금 안 됐을 가능성 높음"으로 구분.
    """
    prompt = {"emotion_type": "smart"}
    if prev_text:
        prompt["previous_text"] = prev_text
    if next_text:
        prompt["next_text"] = next_text
    body = {
        "voice_id": voice_id,
        "text": text,
        "model": "ssfm-v30",
        "language": "kor",
        "prompt": prompt,
        "output": {"audio_format": "wav", "audio_pitch": 0, "audio_tempo": 1, "volume": 100},
        "seed": SEED,
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode("utf-8"),
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read(), "responded"
    except urllib.error.HTTPError as e:
        return e.code, e.read(), "responded"
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        # 응답 자체를 못 받음 — 과금 여부 불확실. 자동 재시도 금지, 사람이 포털에서 확인.
        return None, str(e).encode(), "ambiguous_no_response"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice-id", required=True)
    ap.add_argument("--speaker-name", required=True, help="예: JINWOO, SEOHYEON (폴더명이 됨)")
    ap.add_argument("--corpus", required=True, help="corpus_chunks.json 경로")
    ap.add_argument("--data-dir", required=True, help="출력 루트 (예: data-finetune)")
    ap.add_argument("--api-key-file", default="~/.typecast_key")
    ap.add_argument("--budget-chars", type=int, required=True, help="이 화자에게 쓸 최대 글자수")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    chunks = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    speaker_dir = Path(args.data_dir) / args.speaker_name
    ledger_path = speaker_dir / "_ledger.jsonl"
    ledger = load_ledger(ledger_path)

    already_spent = sum(
        c["char_count"] for c in chunks
        if ledger.get(c["chunk_index"], {}).get("status") == "success"
    )
    print(f"[{args.speaker_name}] 기존 성공 청크로 이미 지출됨: {already_spent}자 "
          f"({sum(1 for r in ledger.values() if r.get('status') == 'success')}건)")

    api_key = None if args.dry_run else load_api_key(args.api_key_file)

    planned: list[dict] = []
    running_total = already_spent
    for chunk in chunks:
        idx = chunk["chunk_index"]
        prior = ledger.get(idx)
        if prior and prior.get("status") == "success":
            continue  # 이미 성공 — 재호출 절대 금지
        cc = chunk["char_count"]
        if running_total + cc > args.budget_chars:
            break  # 예산 초과 직전에 멈춤 (부분 청크 전송 안 함)
        planned.append(chunk)
        running_total += cc

    print(f"[{args.speaker_name}] 이번 실행에서 신규 호출 예정: {len(planned)}건, "
          f"{sum(c['char_count'] for c in planned)}자 "
          f"(누적 예상 {running_total}/{args.budget_chars}자)")

    if args.dry_run:
        for c in planned[:5]:
            print(f"  - #{c['chunk_index']} ({c['char_count']}자): {c['text'][:40]}...")
        if len(planned) > 5:
            print(f"  ... 외 {len(planned) - 5}건")
        print("[dry-run] 실제 API 호출 없음.")
        return

    if not planned:
        print("호출할 신규 청크 없음 (예산 소진 또는 코퍼스 소진). 종료.")
        return

    speaker_dir.mkdir(parents=True, exist_ok=True)
    # 기존 파일 중 가장 큰 인덱스 다음부터 이어서 번호 매김 (재실행 시 파일명 충돌 방지)
    existing_nums = [int(p.stem) for p in speaker_dir.glob("[0-9][0-9][0-9].wav")]
    next_num = (max(existing_nums) + 1) if existing_nums else 1

    success, failed, ambiguous = 0, 0, 0
    spent_chars = 0
    for chunk in planned:
        status, payload, kind = call_typecast(
            api_key, args.voice_id, chunk["text"], chunk["prev_text"], chunk["next_text"],
        )
        ts = time.time()
        if status == 200:
            fname = f"{next_num:03d}"
            (speaker_dir / f"{fname}.wav").write_bytes(payload)
            (speaker_dir / f"{fname}.lab").write_text(chunk["text"], encoding="utf-8")
            append_ledger(ledger_path, {
                "chunk_index": chunk["chunk_index"], "status": "success",
                "http_status": status, "char_count": chunk["char_count"],
                "file": fname, "timestamp": ts,
            })
            print(f"  OK  #{chunk['chunk_index']} -> {fname}.wav ({chunk['char_count']}자)")
            next_num += 1
            success += 1
            spent_chars += chunk["char_count"]
        elif kind == "ambiguous_no_response":
            append_ledger(ledger_path, {
                "chunk_index": chunk["chunk_index"], "status": "ambiguous",
                "error": payload.decode(errors="replace")[:300], "timestamp": ts,
            })
            print(f"  ??  #{chunk['chunk_index']} 응답 없음 — 수동 확인 필요, 자동 재시도 안 함")
            ambiguous += 1
        else:
            append_ledger(ledger_path, {
                "chunk_index": chunk["chunk_index"], "status": "failed",
                "http_status": status, "error": payload.decode(errors="replace")[:300],
                "timestamp": ts,
            })
            print(f"  FAIL #{chunk['chunk_index']} status={status}")
            failed += 1
        time.sleep(REQUEST_INTERVAL_SEC)

    print(f"\n[{args.speaker_name}] 완료: 성공 {success}, 실패 {failed}, 애매함(수동확인) {ambiguous}")
    print(f"  이번 실행 실제 지출(성공분만): {spent_chars}자")


if __name__ == "__main__":
    main()
