#!/usr/bin/env python3
"""
WaggleBot docs linter — 6개 검사.
표준 라이브러리만 사용. 종료코드 0=통과, 1=실패.

검사 항목:
  1) 루트에 허용 외 .md 없음 (CLAUDE.md / README.md / AGENTS.md 만)
  2) docs/ 전체에 C4Context/C4Container/C4Component/C4Dynamic 0건
  3) 모든 ```mermaid 블록 경량 검증 (펜스 균형·비어있지 않음·알려진 다이어그램 타입)
     * 완전 파싱 아님 — 펜스 균형·첫 줄 타입만 확인
  4) docs/_index.md 트리거 맵/계층 인덱스가 가리키는 파일 실재
  5) docs/ 내 상대 마크다운 링크 깨짐 0건
  6) 다이어그램 포함 문서에 last-verified + code-ref 헤더 존재
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DOCS_DIR = ROOT / "docs"

ALLOWED_ROOT_MD = {"CLAUDE.md", "README.md", "AGENTS.md"}

KNOWN_DIAGRAM_TYPES = {
    "flowchart", "graph", "sequenceDiagram", "stateDiagram", "stateDiagram-v2",
    "erDiagram", "gantt", "pie", "classDiagram", "gitGraph", "mindmap",
    "timeline", "quadrantChart", "xychart-beta", "block-beta",
}

FORBIDDEN_C4 = re.compile(r"\bC4Context\b|\bC4Container\b|\bC4Component\b|\bC4Dynamic\b")

# Matches ```mermaid ... ``` blocks (non-greedy)
MERMAID_FENCE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)

# Matches markdown links: [text](path)  — captures the path
MD_LINK = re.compile(r"\[([^\]]*)\]\(([^)#\s]+)(#[^)]*)?\)")

errors: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)
    print(f"  FAIL  {msg}")


def ok(msg: str) -> None:
    print(f"  pass  {msg}")


# ── Check 1: root .md files ──────────────────────────────────────────────────
def check_root_md() -> None:
    print("\n[1] 루트 .md 파일 (심링크 포함 허용)")
    violations = [
        f.name for f in ROOT.glob("*.md")
        if f.name not in ALLOWED_ROOT_MD
    ]
    if violations:
        err(f"루트에 허용 외 .md 발견: {violations}")
    else:
        ok(f"루트 md: {sorted(ALLOWED_ROOT_MD & {f.name for f in ROOT.glob('*.md')})}")


# ── Check 2: no C4 proprietary syntax ───────────────────────────────────────
def check_no_c4_syntax() -> None:
    print("\n[2] C4Context/C4Container/C4Component/C4Dynamic 0건")
    hits: list[str] = []
    for md in DOCS_DIR.rglob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        if FORBIDDEN_C4.search(text):
            hits.append(str(md.relative_to(ROOT)))
    if hits:
        err(f"C4 전용 구문 발견: {hits}")
    else:
        ok("C4 전용 구문 없음")


# ── Check 3: mermaid block lightweight validation ────────────────────────────
def check_mermaid_blocks() -> None:
    print("\n[3] mermaid 블록 경량 검증")
    block_count = 0
    for md in DOCS_DIR.rglob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        # Count fence opens vs closes
        opens = text.count("```mermaid")
        closes_after_open: list[int] = []
        for m in MERMAID_FENCE.finditer(text):
            content = m.group(1).strip()
            block_count += 1
            if not content:
                err(f"{md.relative_to(ROOT)}: 빈 mermaid 블록")
                continue
            first_line = content.splitlines()[0].strip().split()[0] if content.splitlines() else ""
            if first_line not in KNOWN_DIAGRAM_TYPES:
                err(f"{md.relative_to(ROOT)}: 알 수 없는 다이어그램 타입 '{first_line}'")
            closes_after_open.append(1)
        # Fence balance check (non-regex)
        if opens != len(closes_after_open):
            err(f"{md.relative_to(ROOT)}: mermaid 펜스 불균형 (open={opens}, closed={len(closes_after_open)})")
    ok(f"mermaid 블록 {block_count}개 검사 완료")


# ── Check 4: _index.md links resolve ────────────────────────────────────────
def check_index_links() -> None:
    print("\n[4] docs/_index.md 가 가리키는 파일 실재")
    index = DOCS_DIR / "_index.md"
    if not index.exists():
        err("docs/_index.md 없음")
        return
    text = index.read_text(encoding="utf-8", errors="replace")
    missing: list[str] = []
    for m in MD_LINK.finditer(text):
        link_path = m.group(2)
        if link_path.startswith("http"):
            continue
        # Remove trailing slash
        target = (DOCS_DIR / link_path.rstrip("/")).resolve()
        if not target.exists():
            missing.append(link_path)
    if missing:
        err(f"_index.md 대상 파일 없음: {missing}")
    else:
        ok("_index.md 링크 모두 실재")


# ── Check 5: no broken relative links in docs/ ──────────────────────────────
def check_relative_links() -> None:
    print("\n[5] docs/ 내 상대 링크 깨짐 0건")
    broken: list[str] = []
    for md in DOCS_DIR.rglob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        for m in MD_LINK.finditer(text):
            link_path = m.group(2)
            if link_path.startswith("http") or link_path.startswith("mailto"):
                continue
            if link_path.startswith("/"):
                target = ROOT / link_path.lstrip("/")
            else:
                target = (md.parent / link_path).resolve()
            # Allow directory links (trailing slash) by checking existence of path
            if not target.exists():
                broken.append(f"{md.relative_to(ROOT)} → {link_path}")
    if broken:
        err(f"깨진 상대 링크 {len(broken)}건:\n" + "\n".join(f"    {b}" for b in broken))
    else:
        ok(f"상대 링크 깨짐 없음")


# ── Check 6: diagrams have last-verified + code-ref headers ─────────────────
def check_diagram_headers() -> None:
    print("\n[6] 다이어그램 포함 문서에 last-verified + code-ref 헤더 존재")
    missing_header: list[str] = []
    for md in DOCS_DIR.rglob("*.md"):
        text = md.read_text(encoding="utf-8", errors="replace")
        if "```mermaid" not in text:
            continue
        # Check top 20 lines for headers
        header_zone = "\n".join(text.splitlines()[:20])
        has_lv = "last-verified" in header_zone
        has_cr = "code-ref" in header_zone
        if not has_lv or not has_cr:
            missing_what = []
            if not has_lv:
                missing_what.append("last-verified")
            if not has_cr:
                missing_what.append("code-ref")
            missing_header.append(f"{md.relative_to(ROOT)} (없음: {', '.join(missing_what)})")
    if missing_header:
        err(f"헤더 누락 {len(missing_header)}건:\n" + "\n".join(f"    {h}" for h in missing_header))
    else:
        ok("모든 다이어그램 문서에 헤더 존재")


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("WaggleBot docs lint — 6개 검사")
    print("=" * 60)

    check_root_md()
    check_no_c4_syntax()
    check_mermaid_blocks()
    check_index_links()
    check_relative_links()
    check_diagram_headers()

    print("\n" + "=" * 60)
    if errors:
        print(f"FAIL — {len(errors)}개 항목 실패")
        sys.exit(1)
    else:
        print(f"PASS — 6개 검사 모두 통과")
        sys.exit(0)
