#!/usr/bin/env python3
"""타입캐스트 TTS 코퍼스 추출 (v2) — to_narration_text() 정식 경로 사용.

기존 v1은 summary_text JSON을 직접 파싱해 body lines를 공백으로만 이어붙여
문장부호·문단 구조가 사라지는 버그가 있었다. v2는 반드시
Content.get_script().to_narration_text()를 통해 마침표·문단(\n\n) 구조가
보존된 텍스트를 얻은 뒤 문장 단위로 쪼갠다.
"""
import json
import logging
import re
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent))

from db.session import SessionLocal
from db.models import Post, Content
from ai_worker.tts.normalizer import normalize_for_tts

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MIN_CHARS = 80
MAX_CHARS = 150
TARGET_TOTAL_MAX = 4500


def split_sentence_units(block: str) -> list[str]:
    """문장부호 경계로 분할 (fish_client.py._split_sentence_units 이식)."""
    return [
        u.strip() for u in re.split(r'(?<=[.!?…])(?:[ \t]+|$)', block.strip())
        if u.strip()
    ]


def extract_mood_from_text(text: str) -> str:
    sample = text[:200].lower()
    if any(w in sample for w in ['화나', '화가', '빡', '짜증', '분노']):
        return "anger"
    if any(w in sample for w in ['슬프', '울', '눈물', '아파', '괴로']):
        return "sadness"
    if any(w in sample for w in ['걱정', '불안', '두려', '무섭', '공포']):
        return "fear"
    if any(w in sample for w in ['행복', '좋아', '기뻐', '신나', '기쁨']):
        return "joy"
    return "neutral"


def chunk_post_sentences(sentences: list[str], min_chars: int, max_chars: int) -> list[list[str]]:
    """문장 리스트를 2~3문장·80~150자 청크로 그룹핑 (그리디)."""
    chunks: list[list[str]] = []
    current: list[str] = []
    for sent in sentences:
        tentative = current + [sent]
        tentative_len = sum(len(s) for s in tentative) + (len(tentative) - 1)
        current_len = sum(len(s) for s in current) + (len(current) - 1) if current else 0
        if current and (tentative_len > max_chars or len(current) >= 3) and current_len >= min_chars:
            chunks.append(current)
            current = [sent]
        else:
            current = tentative
    if current:
        current_len = sum(len(s) for s in current) + (len(current) - 1)
        if chunks and current_len < min_chars:
            merged = chunks[-1] + current
            merged_len = sum(len(s) for s in merged) + (len(merged) - 1)
            if merged_len <= max_chars + 40:  # 약간의 여유 허용
                chunks[-1] = merged
            else:
                chunks.append(current)
        else:
            chunks.append(current)
    return chunks


def main():
    session = SessionLocal()
    try:
        rows = (
            session.query(Post, Content)
            .join(Content, Post.id == Content.post_id)
            .filter(Post.site_code == "again_spring", Content.summary_text.isnot(None))
            .all()
        )
        logger.info(f"조회된 포스트: {len(rows)}개")

        all_chunks = []
        mood_dist: dict[str, int] = {}
        skipped = 0

        for post, content in rows:
            script = content.get_script()
            if script is None:
                skipped += 1
                continue
            narration = script.to_narration_text()
            if not narration.strip():
                skipped += 1
                continue

            normalized = normalize_for_tts(narration)
            if not normalized:
                skipped += 1
                continue

            mood = extract_mood_from_text(narration)
            mood_dist[mood] = mood_dist.get(mood, 0) + 1

            # 문단(\n\n) 경계는 넘지 않고, 문단 내부만 문장 단위로 청크
            paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]
            post_sentences: list[str] = []
            for para in paragraphs:
                post_sentences.extend(split_sentence_units(para))
            if not post_sentences:
                skipped += 1
                continue

            groups = chunk_post_sentences(post_sentences, MIN_CHARS, MAX_CHARS)
            for idx, group in enumerate(groups):
                text = " ".join(group)
                prev_text = " ".join(groups[idx - 1]) if idx > 0 else ""
                next_text = " ".join(groups[idx + 1]) if idx + 1 < len(groups) else ""
                all_chunks.append({
                    "post_id": post.id,
                    "mood": mood,
                    "chunk_index": len(all_chunks),  # 전역 유일 인덱스 (수집기 장부 키로 씀)
                    "post_chunk_index": idx,
                    "text": text,
                    "prev_text": prev_text,
                    "next_text": next_text,
                    "char_count": len(text),
                })

        total_chars = sum(c["char_count"] for c in all_chunks)
        logger.info(f"초기 청크 수: {len(all_chunks)}, 총 글자수: {total_chars:,}자")

        chunks = all_chunks
        if total_chars > TARGET_TOTAL_MAX:
            kept, running = [], 0
            for c in chunks:
                if running + c["char_count"] > TARGET_TOTAL_MAX:
                    continue
                kept.append(c)
                running += c["char_count"]
            chunks = kept
            total_chars = running
            logger.info(f"목표 상한 초과로 절단: {len(chunks)}개, {total_chars:,}자")

        out_dir = Path(__file__).parent / "data-finetune-plan"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "corpus_chunks.json"
        out_file.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")

        sizes = [c["char_count"] for c in chunks]
        over = [c for c in chunks if c["char_count"] > MAX_CHARS]
        under = [c for c in chunks if c["char_count"] < MIN_CHARS]
        logger.info("=" * 60)
        logger.info(f"최종 청크 수: {len(chunks)}, 총 글자수: {total_chars:,}자")
        if sizes:
            logger.info(f"청크 크기 min/max/avg: {min(sizes)}/{max(sizes)}/{sum(sizes)/len(sizes):.0f}")
        logger.info(f"80~150자 범위 벗어난 청크: 초과 {len(over)}개, 미달 {len(under)}개")
        logger.info(f"감정 분포: {mood_dist}")
        logger.info(f"스킵된 포스트: {skipped}")
        logger.info(f"출력: {out_file}")
        logger.info("샘플 3개:")
        for c in chunks[:3]:
            logger.info(f"  [#{c['chunk_index']}] post={c['post_id']} mood={c['mood']} "
                        f"({c['char_count']}자): {c['text'][:60]}...")
            logger.info(f"     prev: {c['prev_text'][:40] or '(없음)'}")
            logger.info(f"     next: {c['next_text'][:40] or '(없음)'}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
