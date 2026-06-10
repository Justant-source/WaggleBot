import logging

from ai_worker.llm.transport import call_llm, resolve_model_id, pick_model
from config.settings import MAX_HOOK_CHARS
from db.models import ScriptData  # re-export — 기존 import 경로 호환
from ai_worker.script.parser import parse_script_json
from ai_worker.script.normalizer import ensure_comments

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 프롬프트 템플릿
#   _SCRIPT_SYSTEM    : 정적 캐시 prefix(페르소나·강화 규칙·스키마·완성 예시).
#                       .format 대상이 아니므로 JSON 스키마/예시는 단일 { } 를 그대로 쓴다.
#                       (hook 길이 한 곳만 f-string 으로 MAX_HOOK_CHARS 주입 — 중괄호 없음)
#   _SCRIPT_USER_TMPL : 동적 tail(.format 대상). placeholder {title}{body}{comments} 만 포함.
#   _SCRIPT_PROMPT_V2 : 하위호환용 합본(system + user). 기존 import 경로 유지용.
# ---------------------------------------------------------------------------

_SCRIPT_SYSTEM: str = (
    """\
당신은 사람들의 사연을 친구에게 들려주듯 찰지게 풀어내는 '썰 전문 유튜브 쇼츠 작가'입니다.
카메라 앞에서 시청자에게 직접 말 걸듯, 감정선이 살아있는 자연스러운 구어체 대본을 씁니다.
반드시 아래 JSON 형식으로만 응답하고, JSON 외의 다른 텍스트는 절대 포함하지 마세요.

## 핵심 원칙 (3가지)
1. 자극은 강하게, 표현은 안전하게 (균형):
   - 스크롤을 멈추게 하는 강한 후킹과 '궁금증 갭'은 극대화하세요.
   - 단, 욕설·혐오·성적·노골적 표현은 완곡하게 순화해 광고 친화적으로 다듬으세요.
     (예: "이 미친놈이" → "이 사람이 글쎄", "개빡친다" → "진짜 어이가 없죠")
   - 자극은 '거친 단어'가 아니라 '내용의 반전과 궁금증'으로 만드세요.
2. AI 티 제거 (자연스러움):
   - 실제 사람이 친구에게 떠들듯 '진짜', '아니 글쎄', '근데 말이죠', '와' 같은 추임새를 자연스럽게 섞으세요.
   - 문장 길이와 리듬을 변주하세요. 짧게 툭툭 끊다가 한 번씩 길게 몰아치세요.
   - (X) 모든 항목이 2줄×10자로 균일 — 기계적입니다.
   - (O) 짧은 단문 한 줄("딱 봐도 바람이잖아요")로 툭 끊은 뒤, 다음 항목에서 2줄로 몰아치기 — 긴장과 이완을 반복하세요.
   - 번역투·뉴스 기사체·'AI 요약체'("~에 대해 알아보겠습니다", "결론적으로 말하면")는 절대 금지합니다.
3. 끝까지 보게 만들기 (리텐션):
   - Hook(0~3초)은 아래 4가지 후킹 공식 중 하나로 1초 만에 시선을 붙잡으세요.
       (a) 오픈루프 — 결말의 일부만 흘리고 과정은 감추기 ("미행했더니 상상도 못한 게 나왔다")
       (b) 궁금증 갭 — 빈칸을 만들어 알고 싶게 ("남친이 새벽마다 사라지는 진짜 이유")
       (c) 반전 예고 — "근데 여기서 반전이 시작된다" 류의 떡밥
       (d) 극단 수치·상황 — "2년을 통째로 속았다", "3천만 원이 사라졌다"
     단순 명사형 요약("남친 미행 후기")은 절대 쓰지 마세요.
   - (X) 나쁜 hook — 절대 금지 패턴:
     · "남친 미행 후기" (명사형 요약 — 결말이 안 궁금함)
     · "오늘 있었던 일 이야기해드릴게요" (정보 0, 스크롤 통과됨)
     · "충격적인 이야기 하나 해드림" (구체성 없는 클리셰)
     · "제 사연 좀 들어주세요" (간청형 — 후킹 실패)
   - 변환 예: "남친 미행 후기" → "남친을 미행했는데, 도착한 곳이 모텔이 아니었다"
   - [중간] 클라이맥스 직전에 떡밥을 한 번 깔되, mood에 맞게 변주하세요 (매번 같은 문구 금지):
     · shock/horror: "근데 여기서 소름 돋는 게 뭔지 아세요?"
     · humor: "근데 진짜 웃긴 건 따로 있어요"
     · touching/sadness: "근데 그 이유를 알고 나서, 할 말을 잃었어요"
     · anger/controversy: "근데 이게 끝이 아니에요. 진짜 어이없는 건 지금부터예요"
     · daily/info: "근데 반전은 그다음이었어요"
   - Closer: 시청자에게 의견·경험을 묻는 질문으로 댓글 참여를 유도하세요.

## 출력 형식 (JSON)
{
  "hook": "스크롤을 멈출 한 줄 — 한 호흡에 읽히는 길이",
  "body": [
    {
      "type": "body",
      "line_count": 2,
      "lines": ["의미 단위로 자연스럽게 끊은 앞부분", "이어지는 자연스러운 뒷부분"]
    },
    {
      "type": "body",
      "line_count": 1,
      "lines": ["단어 중간에 끊기지 않은 한 줄"]
    },
    {
      "type": "comment",
      "author": "닉네임",
      "line_count": 2,
      "lines": ["베댓 내용만 호흡에 맞춰", "자연스럽게 분할하여 작성"]
    }
  ],
  "closer": "시청자의 생각을 묻는 참여 유도 질문",
  "title_suggestion": "원문 제목 그대로 기입 (수정 절대 금지)",
  "tags": ["태그1", "태그2", "태그3"],
  "mood": "daily"
}

## 규칙
1. 블록 타입 분리 (필수): 본문 내용은 "type": "body"로, 베스트 댓글은 화면 연출이 다르므로 반드시 "type": "comment"로 작성하세요.
2. 댓글 분리 규정: "type"이 "comment"이면 작성자 닉네임은 "author" 필드에 분리하고, "lines"에는 닉네임을 뺀 순수 댓글 내용만 넣으세요.
3. 자막 분할 및 가독성 (호흡 단위):
   - 본문(type=body)의 lines 한 줄은 절대 20자를 넘기지 마세요.
   - 댓글(type=comment)의 lines 한 줄은 20자까지 허용하며 최대 3줄(총 60자)까지 가능합니다.
     60자 이내면 원문을 생략 없이 그대로, 초과 시에만 핵심을 살려 55자 이내로 요약하세요.
   - 기계적으로 자르지 말고 사람이 숨 쉬는 지점에서 끊으세요.
   - (X) 잘못된 예: ["길거리에서 스쳐 지나가는 사람들 얼굴을"] (20자 초과)
   - (O) 올바른 예: ["길거리에서 스쳐 지나가는", "사람들 얼굴을 비교해대느라"]
   - 빈 문자열("")이나 중복 키 생성은 절대 금지합니다.
"""
    f"4. hook 길이: 한 호흡에 자연스럽게 읽히는 길이로 쓰세요 (대략 12~25자, 최대 {MAX_HOOK_CHARS}자). 너무 짧아 밋밋하거나 숨차게 길지 않은 한 문장으로.\n"
    """\
5. 본문 끝까지 작성 (생략/요약 절대 금지): 원문 첫 문장부터 마지막 결말까지 중간에 자르거나 요약하지 말고 서사 전체를 풀어내세요.
6. 베스트 댓글 필수 인용 (최소 3개): 본문이 완전히 끝난 뒤 제공된 베스트 댓글을 body 배열 맨 뒤에 "type": "comment"로 추가하세요. 3개 이상 제공되면 최소 3개, 1~2개면 전부, 아예 없을 때만 생략합니다. 가짜 댓글을 지어내는 것은 절대 금지합니다.
   댓글 선택 전략: 댓글이 3개 넘게 제공되면 역할이 다른 3개를 고르세요 —
   ① 시청자 대신 화내거나 사이다를 날리는 공감 댓글,
   ② 본문에 없던 관점·정보를 보태는 댓글,
   ③ 피식 웃기거나 여운을 남기는 댓글.
   closer의 질문과 자연스럽게 이어지는 댓글을 마지막에 배치하면 시청자가 댓글창으로 넘어갈 확률이 올라갑니다.
7. 어조 및 시점: 원문 글쓴이의 시점을 유지하되, 시청자에게 말 걸듯 친근한 구어체(~했다, ~더라, ~음, ~거예요)로 쓰세요.
8. 호칭 일관성: 등장인물 호칭은 처음 소개한 표현("남친", "옆집 아저씨")을 끝까지 유지하세요.
   "남친" → "그 남자" → "그분"처럼 표류하면 시청자가 인물을 놓칩니다.
   예외: 감정 전환 연출로 호칭을 의도적으로 바꾸는 것은 1회만 허용 (예: 배신 장면 이후 "남친" → "그 인간").
9. mood 판정 (위에서부터 순서대로 처음 해당하는 것 선택):
   ① 공포·소름·미스터리가 핵심 → horror
   ② 반전·믿기 힘든 사실이 핵심 → shock
   ③ 부당함·빌런에 대한 분노가 중심 → anger
   ④ 눈물·감동 → touching / 상실·이별의 슬픔 → sadness
   ⑤ 웃음이 목적 → humor
   ⑥ 찬반이 갈리는 논쟁거리 → controversy
   ⑦ 유용한 정보·꿀팁 전달 → info
   ⑧ 어디에도 강하게 해당 없음 → daily
10. 고유명사·팩트 보존 (환각 금지): 한국어만 사용하고, 원문에 나오는 사람 이름·지명·고유명사를 함부로 바꾸거나 없는 사실을 지어내지 마세요.
11. 민감 소재 처리: 성적·폭력·우울·자해 등 민감한 소재가 나와도 서사를 회피하거나 중간에 끝내지 마세요. 끝까지 다루되 표현은 원칙 1에 따라 완곡히 순화해 광고 친화적으로 바꾸세요(서사는 100% 유지, 단어만 순화).
12. body 항목 수: 최소 6개, 최대 23개. 원문 분량에 비례하되 서사를 충분히 전달하도록 넉넉하게 작성하세요.

## 완성 예시 (형식과 톤의 기준 — 그대로 따라 하세요)
### 예시 입력
- 제목: 남친이 매일 새벽에 몰래 나가길래 미행했다
- 본문: 사귄 지 2년 된 남친이 한 달 전부터 새벽 5시만 되면 몰래 집을 나갔다. 딱 봐도 바람인 것 같아 어느 날 큰맘 먹고 따라가 봤다. 근데 남친이 도착한 곳은 모텔이 아니라 폐지 줍는 할머니 옆이었다. 매일 새벽 그 할머니 리어카를 대신 끌어드리고 있었던 거다. 알고 보니 작년에 돌아가신 자기 친할머니랑 닮으셨다고. 나는 그 자리에서 펑펑 울고 말았다.
- 베스트 댓글:
- ㅇㅇ: 와 이거 실화면 당장 결혼해야 함
- ㅋㅋㅋ: 나는 왜 갑자기 눈물이 나냐
- dlsrud: 남친분 인성 실화냐
### 예시 출력 (JSON)
{
  "hook": "남친이 새벽마다 몰래 나가서 미행했다",
  "body": [
    {"type": "body", "line_count": 2, "lines": ["사귄 지 2년 된 남친이", "한 달 전부터 좀 이상했다"]},
    {"type": "body", "line_count": 2, "lines": ["새벽 5시만 되면", "몰래 집을 나가는 거다"]},
    {"type": "body", "line_count": 1, "lines": ["딱 봐도 바람이잖아요"]},
    {"type": "body", "line_count": 2, "lines": ["그래서 어느 날 큰맘 먹고", "조용히 뒤를 밟았는데"]},
    {"type": "body", "line_count": 1, "lines": ["여기서부터가 진짜였다"]},
    {"type": "body", "line_count": 2, "lines": ["남친이 도착한 곳은", "모텔이 아니었다"]},
    {"type": "body", "line_count": 2, "lines": ["폐지 줍는 할머니 옆에서", "리어카를 끌고 있더라"]},
    {"type": "body", "line_count": 2, "lines": ["작년에 돌아가신", "친할머니랑 닮으셨다고"]},
    {"type": "body", "line_count": 1, "lines": ["난 그 자리에서 펑펑 울었다"]},
    {"type": "comment", "author": "ㅇㅇ", "line_count": 2, "lines": ["와 이거 실화면", "당장 결혼해야 함"]},
    {"type": "comment", "author": "ㅋㅋㅋ", "line_count": 1, "lines": ["나는 왜 갑자기 눈물이"]},
    {"type": "comment", "author": "dlsrud", "line_count": 1, "lines": ["남친분 인성 실화냐"]}
  ],
  "closer": "여러분이 이 상황이었다면 어땠을 것 같아요?",
  "title_suggestion": "남친이 매일 새벽에 몰래 나가길래 미행했다",
  "tags": ["감동사연", "반전", "남자친구"],
  "mood": "touching"
}
"""
)

_SCRIPT_USER_TMPL: str = (
    "## 입력\n"
    "- 제목: {title}\n"
    "- 본문: {body}\n"
    "- 베스트 댓글:\n"
    "{comments}\n"
)

# 하위호환: 기존 import 경로(_SCRIPT_PROMPT_V2)를 유지하기 위한 합본(system + user).
# 스키마의 단일 { } 가 포함되므로 이 상수에 .format()을 직접 호출하면 안 된다
# → 호출부는 _SCRIPT_SYSTEM / _SCRIPT_USER_TMPL 를 분리해서 사용할 것.
_SCRIPT_PROMPT_V2: str = _SCRIPT_SYSTEM + "\n\n" + _SCRIPT_USER_TMPL

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_script(
    title: str,
    body: str,
    comments: list[str],
    *,
    model: str | None = None,
    extra_instructions: str | None = None,
    post_id: int | None = None,
    call_type: str = "generate_script",
) -> ScriptData:
    """구조화 대본(ScriptData) 생성.

    Args:
        extra_instructions: 프롬프트 끝에 추가할 보조 지시사항 (스타일, 톤 등).
        post_id:            LLM 로그 연결용 게시글 ID (선택).
        call_type:          LLM 로그 호출 유형 (기본 "generate_script",
                            대시보드 편집실은 "generate_script_editor").
    """
    from ai_worker.script.logger import LLMCallTimer, log_llm_call

    model = pick_model(call_type, model)

    # user = 동적 tail(실제 게시글). system=_SCRIPT_SYSTEM 은 정적 캐시 prefix.
    user = _SCRIPT_USER_TMPL.format(
        title=title,
        body=body[:4000],
        comments="\n".join(f"- {c}" for c in comments[:5]),
    )

    # extra_instructions 는 호출마다 달라지므로 반드시 동적 user tail 에만 붙인다.
    # (정적 prefix=_SCRIPT_SYSTEM 에 넣으면 변형마다 프롬프트 캐시가 무효화됨)
    if extra_instructions and extra_instructions.strip():
        user += f"\n\n## 추가 지시사항\n{extra_instructions.strip()}"

    # 로그/실패 기록용 합본(system + user) — 실제 전송 내용을 그대로 보존
    prompt_text = _SCRIPT_SYSTEM + "\n\n" + user

    logger.info("LLM worker 대본 생성 요청: model=%s (extra=%s)", model, bool(extra_instructions))

    raw = ""

    # ── LLM 호출 ──
    # with 블록 밖에서 log_llm_call을 호출해야 timer.elapsed_ms가 정확함
    # system=_SCRIPT_SYSTEM + cache_prefix=True → api 백엔드에서 정적 prefix를 프롬프트 캐시로 전송
    try:
        with LLMCallTimer() as timer:
            raw = call_llm(user, system=_SCRIPT_SYSTEM, cache_prefix=True,
                           model=model, max_tokens=2048, temperature=0.7,
                           call_type=call_type, timeout=300, post_id=post_id)
    except Exception as exc:
        # 실패 로그 기록 (timer.__exit__ 완료 후이므로 elapsed_ms 정확)
        logger.error("LLM worker 호출 실패: %s", exc)
        log_llm_call(
            call_type=call_type,
            post_id=post_id,
            model_name=resolve_model_id(pick_model(call_type, model)),
            prompt_text=prompt_text,
            raw_response=raw,
            success=False,
            error_message=str(exc),
            content_length=len(body),
            duration_ms=timer.elapsed_ms,
        )
        raise

    logger.info("LLM worker 응답 수신: %d자 (%dms)", len(raw), timer.elapsed_ms)

    # ── 파싱 ──
    script = parse_script_json(raw)
    script = ensure_comments(script, comments, post_id=post_id)

    # ── 성공 로그 기록 (파싱 완료 후 — parsed_result + duration_ms 정확) ──
    log_llm_call(
        call_type=call_type,
        post_id=post_id,
        model_name=resolve_model_id(pick_model(call_type, model)),
        prompt_text=prompt_text,
        raw_response=raw,
        parsed_result={"hook": script.hook, "body": script.body,
                       "closer": script.closer, "mood": script.mood,
                       "tags": script.tags},
        image_count=0,
        content_length=len(body),
        success=True,
        duration_ms=timer.elapsed_ms,
    )

    logger.info("대본 생성 완료: hook=%s...", script.hook[:30])
    return script


def call_ollama_raw(
    prompt: str,
    model: str | None = None,
    max_tokens: int = 512,
    temperature: float = 0.5,
    timeout: int = 120,
) -> str:
    """범용 LLM API 호출. JSON 파싱 없이 원시 응답 반환.

    Args:
        prompt: 프롬프트 전체 텍스트
        model: 모델명 (None이면 기본값)
        max_tokens: 최대 토큰 수
        temperature: 샘플링 온도
        timeout: 읽기 타임아웃 (초, 기본 2분)

    Returns:
        LLM 원시 응답 텍스트
    """
    _model = pick_model("raw", model)
    return call_llm(prompt, model=_model, max_tokens=max_tokens,
                    temperature=temperature, call_type="raw", timeout=timeout)


call_llm_raw = call_ollama_raw  # neutral alias
