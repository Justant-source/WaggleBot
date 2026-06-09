"""Phase 2: LLM 청킹 (의미 단위 분절)

ResourceProfile을 기반으로 전략별 프롬프트를 생성하고
LLM(Claude) JSON 모드로 구어체 대본을 분절 생성한다.

프롬프트는 정적/동적으로 분리된다:
    - build_chunking_system(): 페르소나·규칙·스키마·완성 예시 (캐시 prefix, 게시글 무관)
    - _build_chunking_user():  자원 상황 + 실제 입력 (동적 tail)
    api 백엔드에서 system을 prompt caching 블록으로 전송해 반복 호출 비용을 줄인다.

출력 형식:
    {
        "hook": "...",
        "body": [
            {"line_count": 2, "lines": ["문장1 앞", "문장1 뒤"]},
            {"line_count": 1, "lines": ["문장2"]},
            ...
        ],
        "closer": "..."
    }
    body 항목의 lines 요소는 각 20자 이내.
    20자 초과 시 어절 단위로 분리해 line_count 2로 설정.
"""
import json
import logging

from ai_worker.llm.transport import call_llm_json, pick_model, resolve_model_id
from ai_worker.scene.analyzer import ResourceProfile
from config.settings import MAX_BODY_CHARS, MAX_HOOK_CHARS, get_llm_constraints_prompt

logger = logging.getLogger(__name__)

_STRATEGY_GUIDE: dict[str, str] = {
    "image_heavy":  "각 문장 짧고 임팩트 있게. 이미지마다 한 문장.",
    "balanced":   "핵심 문장과 보조 문장을 구분해서 작성.",
    "text_heavy": "텍스트만으로 몰입되도록 자세히 작성.",
}


def build_chunking_system(*, extended: bool = False) -> str:
    """LLM 청킹의 정적 캐시 prefix(페르소나·규칙·스키마·완성 예시)를 생성한다.

    게시글/프로필 등 동적 변수는 절대 포함하지 않는다 — 캐시 prefix를 바이트 동일하게
    유지하기 위함. 실제 입력은 _build_chunking_user()의 동적 tail에 들어간다.

    Args:
        extended: True이면 출력 스키마와 완성 예시에 title_suggestion/tags/mood를 포함한다.
    """
    constraints = get_llm_constraints_prompt()

    extended_fields = (
        f'  "title_suggestion": "YouTube 쇼츠 제목 (50자 이내)",\n'
        f'  "tags": ["태그1", "태그2", "태그3"],\n'
        f'  "mood": "humor | touching | anger | sadness | horror | info | controversy | daily | shock 중 하나"\n'
        if extended else ""
    )
    example_extended = (
        '  "title_suggestion": "내 주차자리 뺏은 옆집의 충격 결말",\n'
        '  "tags": ["주차빌런", "아파트", "사이다"],\n'
        '  "mood": "controversy"\n'
        if extended else ""
    )

    return (
        # ── 페르소나 ──
        "당신은 남의 사연을 친구에게 풀어주듯 찰지게 들려주는 '썰 전문 유튜브 쇼츠 내레이터'입니다.\n"
        "항상 1인칭 구어체로, 카메라 앞에서 시청자에게 직접 말을 거는 톤으로 대본을 씁니다.\n"
        "반드시 JSON 형식으로만 응답하며, JSON 외의 텍스트는 절대 포함하지 마세요.\n\n"

        # ── 0. 자연스러움 (가장 중요) ──
        "## 0. 가장 중요 — 자연스러움 (AI가 쓴 티 제거)\n"
        "- 실제 사람이 친구한테 썰 풀듯 말하세요. 매끈한 '글'이 아니라 '말'을 쓰는 겁니다.\n"
        '- "진짜", "와", "아니 글쎄", "근데 있잖아요" 같은 추임새를 자연스럽게 섞으세요.\n'
        "- 문장 길이와 리듬을 변주하세요. 짧게 툭 끊고, 가끔은 길게 몰아치세요.\n"
        "- 번역투·뉴스 기사체·AI 요약체 금지. 정보 나열이 아니라 감정이 실린 '이야기'여야 합니다.\n"
        '  - (X) 뉴스체: "주유소들이 가격을 담합한 것으로 보입니다."\n'
        '  - (O) 구어체: "아니 이 인간들, 지들끼리 가격 짜고 친 거 우리가 모를 줄 알았나 봐요?"\n\n'

        # ── 1. 자극 수위 = 균형 ──
        "## 1. 자극 수위 = 균형 (강하되 안전)\n"
        "- 스크롤을 멈추게 하는 강한 후킹과 궁금증은 최대로 끌어올리세요.\n"
        "- 단, 욕설·혐오·노골적 표현은 방송용으로 순화해 광고 친화적으로 만드세요(노출 제한 방지).\n"
        '  - (X) "이 시벨럼들이" → (O) "이 양아치들이"\n'
        "- 원문의 분노·어이없음·통쾌함 같은 감정은 200% 살리되, 표현만 둥글게 다듬는 겁니다.\n\n"

        # ── 2. 리텐션 설계 ──
        "## 2. 리텐션 설계 (이탈 방지)\n"
        f"- [Hook, 0~3초] 명사형 요약 금지. 아래 후킹 공식 중 하나로 첫 줄부터 꽂으세요(최대 {MAX_HOOK_CHARS}자).\n"
        '  1) 오픈 루프: 결말·정체를 숨겨 궁금하게 — "이거 끝이 진짜 소름입니다"\n'
        '  2) 궁금증 갭: 빈칸을 만들어 채우고 싶게 — "근데 진짜 충격은 따로 있었어요"\n'
        '  3) 반전 예고: 뒤집힘을 약속 — "착한 줄 알았던 그 사람의 정체가..."\n'
        '  4) 극단 수치·단언: 크기로 압도 — "10년 살면서 이런 일은 처음입니다"\n'
        '- [중간] 클라이맥스 직전에 "근데 진짜는 지금부터예요" 같은 떡밥을 한 번 깔고, 감정을 점층시키세요.\n'
        "- [Closer] 시청자에게 의견·경험·판단을 묻는 말로 끝내 댓글 참여를 유도하세요.\n"
        '  - (예) "여러분이라면 어떻게 하실 거예요? 댓글로 알려주세요."\n\n'

        # ── 3. 자막 분할 ──
        "## 3. 자막 분할 (호흡 단위)\n"
        "- 기계적으로 자르지 말고, 사람이 말하며 숨 쉬는 '호흡 단위'로 끊으세요.\n"
        "- 한 줄(lines 요소)은 20자 이내, 의미가 어색하게 끊기지 않게 하세요.\n"
        '  - (O) "정유사들은" / "다 똑같아"   (X) "정유사들" / "은 다 똑같아"\n'
        "- 20자를 넘으면 어절 단위로 나눠 같은 항목의 lines에 담고 line_count를 늘리세요.\n\n"

        # ── 4. 블록·댓글·팩트 ──
        "## 4. 블록·댓글·팩트 규칙\n"
        '- 댓글을 읽어주는 항목에는 "type": "comment"를 추가하고, 일반 본문 항목은 type을 생략합니다.\n'
        '- 댓글은 본문과 별도 body 항목으로 분리하고, lines에 "닉네임: 내용" 형태로 인라인하세요.\n'
        "- 입력에 베스트 댓글이 있으면 반드시 body에 인용하세요.\n"
        "- 댓글도 한 줄 20자 규칙 적용, 최대 3줄(총 60자 이내). 길면 핵심만 추려 요약하세요.\n"
        "- 원문 내용을 끝까지 대본화하세요(생략·요약 금지).\n"
        "- 고유명사·팩트는 그대로 보존하고 환각·오역 금지. 한국어 문맥을 정확히 파악하세요.\n"
        '  - (예: "정유사는 다 틀린데"의 "틀리다"는 영어 "wrong"이 아니라 "다르다(different)"는 구어 표현)\n'
        "- mood는 humor | touching | anger | sadness | horror | info | controversy | daily | shock 중 하나.\n"
        "- body 항목 수는 본문 길이에 비례: 최소 6줄, 최대 30줄(본문 1500자 이상일 때).\n\n"

        # ── 출력 형식 ──
        "## 출력 형식 (JSON)\n"
        "{\n"
        f'  "hook": "첫 3초 후킹 문장 (최대 {MAX_HOOK_CHARS}자)",\n'
        '  "body": [\n'
        '    {"line_count": 2, "lines": ["20자 이하 줄 1", "20자 이하 줄 2"]},\n'
        '    {"line_count": 1, "lines": ["20자 이하 단일 줄"]},\n'
        '    {"line_count": 1, "lines": ["닉네임: 댓글 내용"], "type": "comment"}\n'
        '  ],\n'
        f'  "closer": "마무리 멘트 (최대 {MAX_BODY_CHARS}자)",\n'
        f"{extended_fields}"
        "}\n\n"

        # ── few-shot 완성 예시 ──
        "## 완성 예시 (아래 흐름을 그대로 따라 하세요)\n"
        "[입력 예시]\n"
        "옆집이 맨날 내 지정 주차자리에 차를 댑니다. 경고장을 붙여도 무시하길래 "
        "관리실에 신고했더니, 글쎄 그 집이 관리소장 친척이라 아무 조치도 안 해준대요. "
        "어쩔 수 없이 단지 밖에 차를 대고 다녔는데, 어제 아침에 보니 그 집 차에 누가 "
        "락카로 낙서를 잔뜩 해놨더라고요. (베스트 댓글 — 분노왕: 사이다네요 자업자득 ㅋㅋ)\n\n"
        "[이상적 출력]\n"
        "{\n"
        '  "hook": "내 주차자리 뺏은 옆집, 결말이 소름이에요",\n'
        '  "body": [\n'
        '    {"line_count": 2, "lines": ["옆집이 글쎄", "맨날 내 자리에 주차해요"]},\n'
        '    {"line_count": 2, "lines": ["경고장 붙여도", "그냥 쌩까더라고요"]},\n'
        '    {"line_count": 2, "lines": ["빡쳐서 신고했더니", "돌아온 대답이 가관"]},\n'
        '    {"line_count": 2, "lines": ["글쎄 그 집이", "관리소장 친척이래요"]},\n'
        '    {"line_count": 2, "lines": ["근데 진짜 반전은", "지금부터예요"]},\n'
        '    {"line_count": 2, "lines": ["어제 아침에 보니까", "그 집 차에 낙서가"]},\n'
        '    {"line_count": 1, "lines": ["분노왕: 사이다네요 자업자득 ㅋㅋ"], "type": "comment"}\n'
        '  ],\n'
        '  "closer": "여러분이라면 어떻게 하실 거예요?",\n'
        f"{example_extended}"
        "}\n\n"

        # ── 길이 제약 ──
        f"{constraints}\n"
    )


def _build_chunking_user(post_content: str, profile: ResourceProfile) -> str:
    """게시글/프로필 기반 동적 tail(자원 상황 + 입력)을 생성한다."""
    guide = _STRATEGY_GUIDE.get(profile.strategy, "")
    return (
        "## 자원 상황\n"
        f"- 이미지: {profile.image_count}장 / 예상 문장: {profile.estimated_sentences}개\n"
        f"- 전략: {profile.strategy} — {guide}\n\n"
        "## 입력\n"
        f"{post_content[:2000]}\n"
    )


def create_chunking_prompt(
    post_content: str,
    profile: ResourceProfile,
    *,
    extended: bool = False,
) -> str:
    """정적 prefix + 동적 tail을 합친 전체 청킹 프롬프트를 반환한다.

    실제 LLM 호출은 chunk_with_llm()에서 system/user를 분리해 보내지만,
    로깅·테스트 호환을 위해 이 함수는 합본 문자열을 그대로 제공한다.

    Args:
        extended: True이면 title_suggestion/tags/mood 필드도 출력 형식에 포함한다.
    """
    return (
        build_chunking_system(extended=extended)
        + "\n\n"
        + _build_chunking_user(post_content, profile)
    )


def _call_llm_json_sync(user_prompt: str, system: str, model: str) -> dict:
    return call_llm_json(
        user_prompt,
        model=model,
        call_type="chunk",
        timeout=180,
        system=system,
        cache_prefix=True,
    )


async def chunk_with_llm(
    post_content: str,
    profile: ResourceProfile,
    *,
    post_id: int | None = None,
    extended: bool = False,
) -> dict:
    """ResourceProfile 기반 LLM 청킹을 수행하고 raw 대본 dict를 반환한다.

    Args:
        post_content: 게시글 본문
        profile:      Phase 1에서 생성된 ResourceProfile
        post_id:      LLM 로그 연결용 게시글 ID (선택)
        extended:     True이면 title_suggestion/tags/mood 추가 필드도 반환

    Returns:
        {"hook": str, "body": list[dict], "closer": str}
        body 항목: {"line_count": int, "lines": list[str]}
        extended=True 시 위에 더해 {"title_suggestion": str, "tags": list[str], "mood": str}

    Raises:
        requests.RequestException: LLM 통신 오류
        json.JSONDecodeError: 응답 파싱 실패
        ValueError: 필수 키 누락
    """
    import asyncio
    from ai_worker.script.logger import LLMCallTimer, log_llm_call

    # 정적 prefix(캐시 대상) + 동적 tail(실제 입력) 분리
    system = build_chunking_system(extended=extended)
    user = _build_chunking_user(post_content, profile)
    # 로그 완전성을 위해 합본 프롬프트를 별도로 보관
    prompt = create_chunking_prompt(post_content, profile, extended=extended)
    logger.info("LLM 청킹 요청: 전략=%s, 본문=%d자, extended=%s", profile.strategy, len(post_content), extended)

    raw_str = ""
    result: dict = {}
    success = True
    error_msg: str | None = None

    model = pick_model("chunk")
    with LLMCallTimer() as timer:
        try:
            result = await asyncio.to_thread(_call_llm_json_sync, user, system, model)
            raw_str = json.dumps(result, ensure_ascii=False)
        except Exception as exc:
            success = False
            error_msg = str(exc)
            logger.error("LLM 청킹 실패: %s", exc)
            raise
        finally:
            log_llm_call(
                call_type="chunk",
                post_id=post_id,
                model_name=resolve_model_id(pick_model("chunk")),
                prompt_text=prompt,
                raw_response=raw_str,
                parsed_result=result if result else None,
                strategy=profile.strategy,
                image_count=profile.image_count,
                content_length=len(post_content),
                success=success,
                error_message=error_msg,
                duration_ms=timer.elapsed_ms,
            )

    # 필수 키 검증
    for key in ("hook", "body", "closer"):
        if key not in result:
            raise ValueError(f"LLM 응답에 필수 키 누락: '{key}' | 응답={result}")

    if not isinstance(result["body"], list):
        result["body"] = [str(result["body"])]

    # extended 모드: 선택 필드 기본값 보정
    if extended:
        result.setdefault("title_suggestion", "")
        result.setdefault("tags", [])
        result.setdefault("mood", "funny")
        if not isinstance(result["tags"], list):
            result["tags"] = []

    logger.info(
        "LLM 청킹 완료: hook=%d자, body=%d문장, closer=%d자 (%dms)",
        len(result["hook"]), len(result["body"]), len(result["closer"]), timer.elapsed_ms,
    )
    return result
