#!/usr/bin/env python3
"""5개 실사연을 각 배정된 타입캐스트 보이스로 1회씩 합성 (청킹 없음, 완결된 사연)."""
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.typecast.ai/v1/text-to-speech"
API_KEY = Path("/tmp/.typecast_key").read_text().strip()

VOICE_IDS = {
    "JINWOO": "tc_632293f759d649937b97f323",
    "SEOHYEON": "tc_69f2e455ea79fd197aa0476f",
    "HYOEUN": "tc_691d49ccc47926d741f15913",
    "KANGIL": "tc_68d4b115f0486108a7eefb37",
    "KYUNGHWA": "tc_5feb213228b7247f8c8eb6d9",
}

OUT_DIR = Path("/app/data-finetune/five_stories_typecast")
OUT_DIR.mkdir(parents=True, exist_ok=True)

stories = json.loads(Path("/app/data-finetune-plan/five_stories.json").read_text())

total_spent = 0
for s in stories:
    speaker = s["speaker"]
    voice_id = VOICE_IDS[speaker]
    text = s["text"]
    body = {
        "voice_id": voice_id,
        "text": text,
        "model": "ssfm-v30",
        "language": "kor",
        "prompt": {"emotion_type": "smart"},
        "output": {"audio_format": "wav", "audio_pitch": 0, "audio_tempo": 1, "volume": 100},
        "seed": 42,
    }
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode("utf-8"),
        headers={"X-API-KEY": API_KEY, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = resp.read()
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
        data = e.read()

    if status == 200:
        out_wav = OUT_DIR / f"{speaker}_{s['post_id']}.wav"
        out_lab = OUT_DIR / f"{speaker}_{s['post_id']}.lab"
        out_wav.write_bytes(data)
        out_lab.write_text(text, encoding="utf-8")
        total_spent += s["char_count"]
        print(f"OK {speaker} ({s['char_count']}자) -> {out_wav.name}")
    else:
        print(f"FAIL {speaker} status={status} body={data[:200]}")
    time.sleep(0.5)

print(f"\n총 지출: {total_spent}자")
