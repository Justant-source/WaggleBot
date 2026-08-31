#!/usr/bin/env python3
"""
타입캐스트 TTS 코퍼스 추출 스크립트 (최종).

다시봄(Again Spring)의 summary_text 데이터를 타입캐스트용 TTS 코퍼스로 준비.
- DB 조회: site_code='again_spring' & summary_text IS NOT NULL
- 파싱: summary_text JSON → script body lines
- 정규화: normalize_for_tts()
- 청크: 모든 가능한 2~3문장 조합 추출 (범위 무제한)
- 목표: 4,000~4,500자 범위 내 — 초과 시 긴 청크부터 절단
- 출력: corpus_chunks.json
"""

import json
import logging
import re
import sys
from pathlib import Path
from typing import Optional

# worker 디렉토리를 sys.path에 추가
_SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(_SCRIPT_DIR))
sys.path.insert(0, str(_SCRIPT_DIR.parent))

from db.session import SessionLocal
from db.models import Post, Content, PostStatus
from ai_worker.tts.normalizer import normalize_for_tts

logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────
# 문장 쪼개기 (fish_client.py 로직 이식)
# ────────────────────────────────────────────────────────────────
def split_sentence_units(block: str) -> list[str]:
    """Keep sentence punctuation with its preceding unit for natural prosody."""
    return [
        unit.strip()
        for unit in re.split(r'(?<=[.!?…])(?:[ \t]+|$)', block.strip())
        if unit.strip()
    ]


def extract_mood_from_text(text: str) -> str:
    """첫 200자에서 감정 추정 (간단한 휴리스틱)."""
    sample = text[:200].lower()
    if any(w in sample for w in ['화나', '화가', '빡', '짜증', '분노', '욕', '화가나']):
        return "anger"
    elif any(w in sample for w in ['슬프', '울', '눈물', '마음', '아파', '괴로', '비극']):
        return "sadness"
    elif any(w in sample for w in ['걱정', '불안', '두려', '무섭', '깜짝', '공포']):
        return "fear"
    elif any(w in sample for w in ['행복', '좋아', '기뻐', '신나', '웃음', '기쁨', '희락']):
        return "joy"
    else:
        return "neutral"


def parse_script_text(summary_text_json: str) -> str:
    """
    summary_text JSON에서 실제 나레이션 텍스트 추출.

    구조:
    {
      "hook": "...",
      "body": [
        {"lines": ["line1", "line2", ...]},
        ...
      ],
      "closer": "...",
      ...
    }

    body의 모든 lines를 공백으로 연결해서 반환.
    """
    try:
        data = json.loads(summary_text_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    texts = []

    # hook
    if isinstance(data, dict) and data.get("hook"):
        texts.append(str(data["hook"]))

    # body
    if isinstance(data, dict) and data.get("body"):
        body = data["body"]
        if isinstance(body, list):
            for item in body:
                if isinstance(item, dict) and item.get("lines"):
                    lines = item["lines"]
                    if isinstance(lines, list):
                        texts.extend(str(line) for line in lines if line)

    # closer
    if isinstance(data, dict) and data.get("closer"):
        texts.append(str(data["closer"]))

    return " ".join(texts)


# ────────────────────────────────────────────────────────────────
# 메인 로직
# ────────────────────────────────────────────────────────────────
def main():
    """타입캐스트 코퍼스 추출 및 JSON 저장."""

    session = SessionLocal()
    try:
        # DB 쿼리: again_spring 사이트의 summary_text가 있는 포스트
        posts_with_content = (
            session.query(Post, Content)
            .join(Content, Post.id == Content.post_id)
            .filter(
                Post.site_code == 'again_spring',
                Content.summary_text.isnot(None),
            )
            .all()
        )

        logger.info(f"조회된 포스트: {len(posts_with_content)}개")

        if not posts_with_content:
            logger.warning("조회된 포스트가 없습니다. 종료.")
            return

        # ────────────────────────────────────────────────────────────────
        # 청크 생성 (범위 무제한)
        # ────────────────────────────────────────────────────────────────
        all_chunks = []
        mood_dist = {}
        skipped = 0

        for post, content in posts_with_content:
            raw_text = content.summary_text
            if not raw_text or not raw_text.strip():
                skipped += 1
                continue

            # JSON 파싱해서 실제 텍스트 추출
            text = parse_script_text(raw_text)
            if not text or not text.strip():
                skipped += 1
                continue

            # 정규화
            normalized = normalize_for_tts(text)
            if not normalized:
                skipped += 1
                continue

            mood = extract_mood_from_text(text)
            mood_dist[mood] = mood_dist.get(mood, 0) + 1

            # 문장 쪼개기
            sentences = split_sentence_units(normalized)
            if not sentences:
                skipped += 1
                continue

            # 모든 가능한 2~3문장 청크 생성 (범위 무제한)
            chunk_index = 0
            i = 0
            while i < len(sentences):
                chunk_sentences = []
                chunk_text = ""

                # 2~3문장 묶기
                for _ in range(3):
                    if i >= len(sentences):
                        break
                    sent = sentences[i].strip()
                    if not sent:
                        i += 1
                        continue
                    if chunk_text:
                        candidate = chunk_text + " " + sent
                    else:
                        candidate = sent

                    chunk_text = candidate
                    chunk_sentences.append(sent)
                    i += 1

                # 최소 1문장 필요
                if not chunk_text:
                    continue

                # prev_text / next_text 추출
                prev_text = ""
                next_text = ""

                if i - len(chunk_sentences) > 0:
                    prev_idx = i - len(chunk_sentences) - 1
                    prev_text = sentences[prev_idx].strip() if prev_idx >= 0 else ""

                if i < len(sentences):
                    next_text = sentences[i].strip() if i < len(sentences) else ""

                char_count = len(chunk_text)
                all_chunks.append({
                    "post_id": post.id,
                    "mood": mood,
                    "chunk_index": chunk_index,
                    "text": chunk_text,
                    "prev_text": prev_text,
                    "next_text": next_text,
                    "char_count": char_count,
                })
                chunk_index += 1

        # ────────────────────────────────────────────────────────────────
        # 4,000~4,500자 범위 조정: 초과 시 긴 청크부터 제거
        # ────────────────────────────────────────────────────────────────
        chunks = all_chunks[:]
        total_chars = sum(c["char_count"] for c in chunks)

        logger.info(f"  초기 청크 수: {len(chunks)}, 총 글자수: {total_chars:,}자")

        if total_chars > 4500:
            # 긴 청크부터 제거
            sorted_chunks = sorted(chunks, key=lambda c: c["char_count"], reverse=True)
            for chunk_to_remove in sorted_chunks:
                if total_chars <= 4500:
                    break
                chunks.remove(chunk_to_remove)
                total_chars -= chunk_to_remove["char_count"]
            logger.info(f"  조정 후 청크 수: {len(chunks)}, 총 글자수: {total_chars:,}자 (초과 제거)")

        # ────────────────────────────────────────────────────────────────
        # 출력
        # ────────────────────────────────────────────────────────────────
        output_dir = Path(__file__).parent / "data-finetune-plan"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / "corpus_chunks.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(chunks, f, ensure_ascii=False, indent=2)

        # ────────────────────────────────────────────────────────────────
        # 통계
        # ────────────────────────────────────────────────────────────────
        logger.info("=" * 60)
        logger.info(f"포스트 수: {len(posts_with_content)}")
        logger.info(f"스킵된 포스트: {skipped}")
        logger.info(f"청크 수: {len(chunks)}")
        logger.info(f"총 글자수: {total_chars:,}자")
        logger.info(f"목표 범위: 4,000~4,500자")

        if total_chars < 4000:
            logger.warning(f"⚠️  총 글자수 {total_chars:,}자 < 4,000자 (부족 △{4000-total_chars}자)")
        elif total_chars > 4500:
            logger.warning(f"⚠️  총 글자수 {total_chars:,}자 > 4,500자 (초과 △{total_chars-4500}자)")
        else:
            logger.info(f"✓ 범위 내 ({total_chars:,}자)")

        logger.info(f"감정 분포: {mood_dist}")
        logger.info(f"출력 파일: {output_file}")

        # 샘플 3개 출력
        if chunks:
            logger.info("\n샘플 청크 (처음 3개):")
            for idx, sample in enumerate(chunks[:3]):
                logger.info(f"  [{idx+1}] post_id={sample['post_id']} mood={sample['mood']} char={sample['char_count']}")
                logger.info(f"      text: {sample['text'][:70]}...")
                prev_show = sample['prev_text'][:35] if sample['prev_text'] else '(첫문장)'
                next_show = sample['next_text'][:35] if sample['next_text'] else '(마지막)'
                logger.info(f"      prev: {prev_show}...")
                logger.info(f"      next: {next_show}...")

        logger.info("=" * 60)
        logger.info("완료!")

    finally:
        session.close()


if __name__ == "__main__":
    main()
