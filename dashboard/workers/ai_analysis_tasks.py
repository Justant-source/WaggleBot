"""AI 적합도 분석 백그라운드 워커."""

import json
import logging
import re
import threading
import time as _time
from typing import Any

log = logging.getLogger(__name__)

# post_id → {"status": "running"|"done"|"error", "result": dict, "error": str}
_analysis_tasks: dict[int, dict[str, Any]] = {}
_task_lock = threading.Lock()
_task_created_at: dict[int, float] = {}
_TASK_TTL_SECONDS = 300  # 완료/오류 태스크 5분 후 자동 삭제


def _gc_analysis_tasks() -> None:
    """완료/오류된 분석 태스크를 TTL 기반으로 정리."""
    now = _time.time()
    with _task_lock:
        for pid in list(_task_created_at):
            elapsed = now - _task_created_at[pid]
            status = _analysis_tasks.get(pid, {}).get("status")
            if status in ("done", "error") and elapsed > _TASK_TTL_SECONDS:
                _analysis_tasks.pop(pid, None)
                _task_created_at.pop(pid, None)


def get_analysis_task(post_id: int) -> dict | None:
    return _analysis_tasks.get(post_id)


def clear_analysis_task(post_id: int) -> None:
    _analysis_tasks.pop(post_id, None)
    _task_created_at.pop(post_id, None)


def submit_analysis_task(post_id: int, title: str, content: str, model: str) -> bool:
    """분석 작업을 백그라운드 스레드에 제출. 이미 실행 중이면 False 반환."""
    _gc_analysis_tasks()
    with _task_lock:
        existing = _analysis_tasks.get(post_id)
        if existing and existing["status"] == "running":
            return False
        _analysis_tasks[post_id] = {"status": "running"}
        _task_created_at[post_id] = _time.time()

    def _run() -> None:
        try:
            from ai_worker.script.client import call_ollama_raw
            prompt = (
                "다음 게시글의 YouTube 쇼츠 영상 적합도를 분석하세요.\n\n"
                f"제목: {title}\n"
                f"내용: {content[:300]}\n\n"
                "반드시 아래 JSON 형식으로만 응답하세요 (다른 텍스트 금지):\n"
                '{"score": 7, "reason": "판단 근거 요약 2~3문장", "issues": ["문제점1"]}\n\n'
                "평가 기준:\n"
                "- 논쟁적·공감적 주제: +3점\n"
                "- 강한 감정 반응 유발(분노·감동·웃음): +3점\n"
                "- 댓글 활성화 가능성: +2점\n"
                "- 이미지 있음: +1점\n"
                "- 민감·저작권·광고 문제: -3점\n"
                'issues 예시: ["광고성 게시글", "저작권 이미지", "민감 주제", "정치적 내용"]\n'
                "문제 없으면 issues는 [] 로 작성"
            )
            raw = call_ollama_raw(prompt=prompt, model=model)
            m = re.search(r"\{.*?\}", raw, re.DOTALL)
            result = json.loads(m.group()) if m else {
                "score": 0, "reason": "파싱 실패", "issues": []
            }
            with _task_lock:
                _analysis_tasks[post_id] = {"status": "done", "result": result}
        except Exception as exc:
            log.warning("AI 적합도 분석 실패 post_id=%d: %s", post_id, exc)
            with _task_lock:
                _analysis_tasks[post_id] = {
                    "status": "error",
                    "error": str(exc),
                    "result": {"score": 0, "reason": "분석 실패", "issues": []},
                }

    threading.Thread(target=_run, daemon=True).start()
    return True
