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
        f'  "mood": "humor | touching | anger | sadness | horror | info | controversy | daily | shock 중 하나",\n'
        f'  "narrator_gender": "male | female",\n'
        f'  "narrator_age": "10s | 20s | 30s | 40s | 50s | 60s",\n'
        f'  "chat_messages": [{{"sender": "나", "text": "메시지 원문", "is_mine": true}}, ...] or null\n'
        if extended else ""
    )
    example_extended = (
        '  "title_suggestion": "내 주차자리 뺏은 옆집의 충격 결말",\n'
        '  "tags": ["주차빌런", "아파트", "사이다"],\n'
        '  "mood": "controversy",\n'
        '  "narrator_gender": "female",\n'
        '  "narrator_age": "30s",\n'
        '  "chat_messages": null\n'
        if extended else ""
    )

    return (
        # ── 페르소나 ──
        "당신은 남의 사연을 친구에게 풀어주듯 찰지게 들려주는 '썰 전문 유튜브 쇼츠 내레이터'입니다.\n"
        "항상 1인칭 구어체로, 카메라 앞에서 시청자에게 직접 말을 거는 톤으로 대본을 씁니다.\n"
        "당신의 유일한 성공 지표는 시청자가 영상을 마지막 1초까지 보게 만드는 것입니다.\n"
        "반드시 JSON 형식으로만 응답하며, JSON 외의 텍스트는 절대 포함하지 마세요.\n\n"

        # ── 0. 자연스러움 (가장 중요) ──
        "## 0. 가장 중요 — 자연스러움 (AI가 쓴 티 제거)\n"
        "- 실제 사람이 친구한테 썰 풀듯 말하세요. 매끈한 '글'이 아니라 '말'을 쓰는 겁니다.\n"
        '- "진짜", "와", "아니 글쎄", "근데 있잖아요" 같은 추임새를 자연스럽게 섞으세요.\n'
        "- 문장 길이와 리듬을 변주하세요. 짧게 툭 끊고, 가끔은 길게 몰아치세요.\n"
        '- (X) 모든 항목이 2줄×10자로 균일 — 기계적입니다.\n'
        '- (O) 짧은 단문 한 줄("딱 봐도 바람이잖아요")로 툭 끊은 뒤, 다음 항목에서 2줄로 몰아치기 — 긴장과 이완을 반복하세요.\n'
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
        "## 2. 리텐션 설계 (이탈 방지 — 가장 중요)\n"
        "쇼츠는 첫 1초에 멈추게 하고, 끝까지 답을 안 주며 끌고 가는 게임입니다. 아래 7개를 모두 적용하세요.\n\n"

        # 2-1 Hook
        f"### 2-1. Hook 강화 [0~3초, 최대 {MAX_HOOK_CHARS}자]\n"
        "아래 공식 중 하나로 첫 줄부터 꽂으세요. **첫 어절에 가장 강한 단어를 두고**(끝에 두지 말 것), "
        "**구체 명사 또는 숫자를 1개 이상** 반드시 넣으세요.\n"
        '  1) 오픈 루프: 결말·정체를 숨겨 궁금하게 — "남친 폰에서 본 사진 한 장에 무너졌어요"\n'
        '  2) 궁금증 갭: 빈칸을 만들어 채우고 싶게 — "2년 사귄 남친의 진짜 정체"\n'
        '  3) 반전 예고: 뒤집힘을 약속 — "착한 줄 알았던 그 사람의 정체가..."\n'
        '  4) 극단 수치·단언: 크기로 압도 — "10년 살면서 이런 일은 처음입니다"\n'
        '  5) 1인칭 고백·후회형: 감정으로 끌기 — "그날 신고 안 한 거, 아직도 후회해요"\n'
        "- (X) 나쁜 hook — 절대 금지 패턴:\n"
        '  · "남친 미행 후기" (명사형 요약 — 결말이 안 궁금함)\n'
        '  · "오늘 있었던 일 이야기해드릴게요" (정보 0, 스크롤 통과됨)\n'
        '  · "충격적인 이야기 하나 해드림" (구체성 없는 클리셰)\n'
        '  · "제 사연 좀 들어주세요" (간청형 — 후킹 실패)\n'
        '- 변환 예: "남친 미행 후기" → "남친 미행했는데 도착한 곳이 모텔이 아니었어요"\n\n'

        # 2-2 Hook-Payoff 계약
        "### 2-2. Hook-Payoff 계약 (핵심 원리)\n"
        "- hook이 연 궁금증의 답(payoff)은 **body 마지막 1/3 구간에서만** 풀어주세요.\n"
        "- 초반 블록에서 결말·정체의 단서를 미리 흘리면 시청자가 바로 이탈합니다.\n"
        "- 단, hook이 약속한 답은 대본 안에서 **반드시** 줘야 합니다. 어그로만 끌고 답 없이 끝내는 낚시는 금지(신고·이탈 유발).\n"
        '  - (X) hook에서 "정체가..."라 해놓고 본문에서 안 밝힘 / (O) 마지막 블록에서 정체를 터뜨림\n\n'

        # 2-3 에스컬레이션 체인
        "### 2-3. 에스컬레이션 체인 (블록 연결)\n"
        '- 블록을 "그리고/그래서"로 단순 나열하지 마세요. "근데/그런데/알고 보니/문제는/여기서부터가"로 전환·고조하세요.\n'
        "- 매 2~3블록마다 새 정보·반전·감정 전환 중 하나가 나와 긴장이 계속 세지게 하세요.\n"
        '  - (X) "갔어요. 그리고 봤어요. 그리고 말했어요" (밋밋한 나열)\n'
        '  - (O) "갔어요. 근데 문이 열려 있더라고요. 알고 보니…" (점점 고조)\n\n'

        # 2-4 블록 클리프행어
        "### 2-4. 블록 클리프행어\n"
        '- 긴장이 걸린 지점에서 블록을 일부러 미완으로 끊어 다음 줄을 듣게 만드세요 ("…열어봤는데", "도착한 곳은").\n'
        "- 단, §3의 호흡 단위 규칙은 지키세요 — 어절 중간이 아니라 의미가 매달리는 지점에서 끊습니다.\n\n"

        # 2-5 감정 낙차
        "### 2-5. 감정 낙차\n"
        "- payoff 직전 블록은 일부러 평온·일상 톤으로 낮췄다가, 다음 블록에서 떨어뜨리세요 (평온→충격, 웃음→소름).\n"
        "- 대비가 클수록 시청자의 감정 반응(도파민)이 커집니다.\n\n"

        # 2-6 중간 떡밥
        "### 2-6. 중간 떡밥\n"
        "- payoff 직전(클라이맥스 직전)에 떡밥을 한 번 까세요.\n"
        '- 핵심: "지금부터예요" 같은 막연한 마무리는 쓰지 말고, 떡밥 안에 사연의 구체 단어'
        "(인물·사물·반전 대상)를 넣어 무엇이 터질지 살짝 흘리세요.\n"
        '  - (X) 막연(금지): "근데 진짜 어이없는 건 지금부터예요"\n'
        '  - (O) 구체: "근데 진짜 어이없는 건 시어머니가 한 말이에요" / "근데 그 카톡 한 줄이 다 뒤집었어요"\n'
        "- 아래는 mood별 '톤'일 뿐입니다 — 문구를 그대로 복붙하지 말고 위처럼 사연 단어를 넣어 매번 새로 쓰세요:\n"
        "  · shock/horror: 소름·등골 서늘 톤   · humor: 빵 터지는·웃긴 포인트 톤\n"
        "  · touching/sadness: 코끝 찡한·할 말 잃은 톤   · anger/controversy: 어이없는·기가 막힌 톤\n"
        "  · daily/info: 반전·생각이 확 바뀐 톤\n\n"

        # 2-7 Closer
        f"### 2-7. Closer [최대 {MAX_BODY_CHARS}자 — 초과 시 잘림]\n"
        "댓글 참여를 유도하는 한 문장으로 끝내세요. 우선순위:\n"
        '  ① 편가르기·선택강요형: "이거 제가 예민한 거예요?", "사이다예요 범죄예요?"\n'
        '  ② 루프형: hook의 질문을 되받아 처음과 연결\n'
        '  ③ 열린 질문(차선): "여러분이라면 어떻게 하실 거예요?"\n'
        "- 단, 편가르기는 의견 대립 수준까지만. 혐오·정치 편가르기는 금지.\n"
        "- 아동·노약자·동물 등 약자에 대한 명백한 학대·폭력은 찬반 투표형 편가르기로 만들지 마세요"
        '(\"훈육이냐 학대냐\" 식 금지). 피해자 보호·공감 관점의 질문으로 대체하세요.\n\n'

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
        "- 댓글이 3개 넘게 제공되면 역할이 다른 3개를 고르세요 —\n"
        "  ① 시청자 대신 화내거나 사이다를 날리는 공감 댓글,\n"
        "  ② 본문에 없던 관점·정보를 보태는 댓글,\n"
        "  ③ 피식 웃기거나 여운을 남기는 댓글.\n"
        "  closer의 질문과 자연스럽게 이어지는 댓글을 마지막에 배치하면 시청자가 댓글창으로 넘어갈 확률이 올라갑니다.\n"
        "- 댓글도 한 줄 20자 규칙 적용, 최대 3줄(총 60자 이내). 길면 핵심만 추려 요약하세요.\n"
        "- 원문 내용을 끝까지 대본화하세요(생략·요약 금지).\n"
        "- 고유명사·팩트는 그대로 보존하고 환각·오역 금지. 한국어 문맥을 정확히 파악하세요.\n"
        '  - (예: "정유사는 다 틀린데"의 "틀리다"는 영어 "wrong"이 아니라 "다르다(different)"는 구어 표현)\n'
        "- 실존 개인 식별정보 익명화: 사건·사고·의료·법적 분쟁 등 실제 피해자·가해자가 등장하는 글에서는 "
        '실명·나이·연락처·상세 주소 같은 식별정보를 가리세요 (예: "강찬규 씨, 59세" → "60대 남성 A씨"). '
        "서사·사실관계·시간순은 100% 보존하되, '누구인지'만 가립니다. "
        "글쓴이 본인·가족 호칭(남편·시어머니 등)과 공인·기관·기업·지역명은 그대로 둡니다.\n"
        "- 등장인물 호칭은 처음 소개한 표현을 끝까지 유지하세요. "
        '"남친" → "그 남자" → "그분"처럼 표류하면 시청자가 인물을 놓칩니다. '
        "예외: 감정 전환 연출로 호칭을 의도적으로 바꾸는 것은 1회만 허용 (예: 배신 장면 이후 \"남친\" → \"그 인간\").\n"
        "- **화자 태깅 (다중 음성)**: 본문 중 다른 인물의 **직접 발화**(카톡, 대화, 인용문)는 별도 body 항목으로 분리하고 "
        '`"speaker": "character"`, `"character_label"`, `"character_gender"`, `"character_age"` 4개 필드를 추가하세요. '
        "내레이터가 서술하는 문장은 speaker 생략(기본 narrator). 같은 인물은 동일 character_label을 반드시 사용하세요.\n"
        "## 5. 대화 캡처 추출 (chat_messages)\n"
        "- 본문에 카카오톡·문자·DM 등 **실제 메시지 대화 로그**가 포함되어 있으면 `chat_messages` 배열을 채우세요.\n"
        "- 각 항목: `{\"sender\": \"나\", \"text\": \"메시지 원문\", \"is_mine\": true}` — 보낸이가 글쓴이·사연자이면 `is_mine:true`, 상대방이면 `false`.\n"
        "- 대화 원문을 최대한 그대로 가져오세요 (재구성·요약 금지). 단 개인정보(실명·연락처)는 익명화.\n"
        "- 이야기의 핵심 반전·사이다·갈등이 드러나는 메시지 최대 8개를 선택하세요.\n"
        "- 대화 로그가 없거나 추출 불필요하면 `\"chat_messages\": null`로 두세요.\n\n"
        "- mood 판정 (위에서부터 순서대로 처음 해당하는 것 선택):\n"
        "  ① 공포·소름·미스터리가 핵심 → horror\n"
        "  ② 반전·믿기 힘든 사실이 핵심 → shock\n"
        "  ③ 부당함·빌런에 대한 분노가 중심 → anger\n"
        "  ④ 눈물·감동 → touching / 상실·이별의 슬픔 → sadness\n"
        "  ⑤ 웃음이 목적 → humor\n"
        "  ⑥ 찬반이 갈리는 논쟁거리 → controversy\n"
        "  ⑦ 유용한 정보·꿀팁 전달 → info\n"
        "  ⑧ 어디에도 강하게 해당 없음 → daily\n"
        "- body 항목 수는 본문 길이에 비례: 최소 6줄, 최대 30줄(본문 1500자 이상일 때).\n\n"

        # ── 출력 형식 ──
        "## 출력 형식 (JSON)\n"
        "{\n"
        f'  "hook": "첫 3초 후킹 문장 (최대 {MAX_HOOK_CHARS}자)",\n'
        '  "body": [\n'
        '    {"line_count": 2, "lines": ["20자 이하 줄 1", "20자 이하 줄 2"]},\n'
        '    {"line_count": 1, "lines": ["20자 이하 단일 줄"]},\n'
        '    {"line_count": 1, "lines": ["닉네임: 댓글 내용"], "type": "comment"},\n'
        '    {"line_count": 1, "lines": ["대사 내용"], "speaker": "character", "character_label": "등장인물명(예:남자친구)", "character_gender": "male|female", "character_age": "20s|30s|..."}\n'
        '  ],\n'
        f'  "closer": "마무리 멘트 (최대 {MAX_BODY_CHARS}자)",\n'
        f"{extended_fields}"
        "}\n\n"

        # ── few-shot 완성 예시 ──
        "## 완성 예시 (리텐션 곡선을 그대로 따라 하세요)\n"
        "[입력 예시]\n"
        "- 제목: 내 주차자리에 맨날 차 대는 옆집 결국...\n"
        "- 본문: 옆집이 맨날 내 지정 주차자리에 차를 댑니다. 경고장을 붙여도 무시하길래 "
        "관리실에 신고했더니, 글쎄 그 집이 관리소장 친척이라 아무 조치도 안 해준대요. "
        "어쩔 수 없이 단지 밖에 차를 대고 다녔는데, 어제 아침에 보니 그 집 차에 누가 "
        "락카로 낙서를 잔뜩 해놨더라고요.\n"
        "- 베스트 댓글:\n"
        "  - 분노왕: 사이다네요 자업자득 ㅋㅋ\n"
        "  - 정의구현: 관리소장도 같이 책임져야죠\n"
        "  - 웃참실패: 낙서범한테 표창 줘야 함\n\n"
        "[이상적 출력]  ← hook은 결말(낙서)을 숨기고, payoff는 마지막 1/3에서 터뜨림. 평온→고조→클리프행어 곡선.\n"
        "{\n"
        '  "hook": "1년 참은 주차 빌런, 결말이 소름이에요",\n'
        '  "body": [\n'
        '    {"line_count": 2, "lines": ["옆집이 글쎄", "맨날 내 자리에 주차해요"]},\n'
        '    {"line_count": 2, "lines": ["처음엔 그냥", "좋게 넘어갔거든요"]},\n'
        '    {"line_count": 2, "lines": ["근데 경고장을 붙여도", "그냥 쌩까더라고요"]},\n'
        '    {"line_count": 2, "lines": ["빡쳐서 신고했더니", "돌아온 대답이 가관"]},\n'
        '    {"line_count": 2, "lines": ["글쎄 그 집이", "관리소장 친척이래요"]},\n'
        '    {"line_count": 2, "lines": ["어쩔 수 없이 그냥", "단지 밖에 댔어요"]},\n'
        '    {"line_count": 2, "lines": ["근데 어제 아침", "내 눈을 의심했어요"]},\n'
        '    {"line_count": 2, "lines": ["그 집 차에 누가", "락카로 낙서를"]},\n'
        '    {"line_count": 1, "lines": ["온통 칠해놨더라고요"]},\n'
        '    {"line_count": 1, "lines": ["분노왕: 사이다네요 자업자득 ㅋㅋ"], "type": "comment"},\n'
        '    {"line_count": 1, "lines": ["정의구현: 관리소장도 책임져야죠"], "type": "comment"},\n'
        '    {"line_count": 1, "lines": ["웃참실패: 낙서범한테 표창 줘야 함"], "type": "comment"}\n'
        '  ],\n'
        '  "closer": "낙서범, 사이다예요 범죄예요?",\n'
        f"{example_extended}"
        "}\n\n"

        # ── 출력 전 자가점검 ──
        "## 출력 전 자가점검 (JSON 출력 직전 확인)\n"
        "① hook이 연 궁금증의 답이 body 마지막 1/3에 있는가? (초반에 결말 노출 금지)\n"
        '② "그리고"로 단순 나열한 블록이 없는가? ("근데/알고 보니"로 고조했는가)\n'
        "③ hook은 40자 이내, 모든 lines·closer는 20자 이내인가?\n"
        "확인 후 JSON만 출력하세요.\n\n"

        # ── 길이 제약 ──
        f"{constraints}\n"
    )


def _build_chunking_user(
    post_content: str,
    profile: ResourceProfile,
    *,
    title: str = "",
    best_comments: list[str] | None = None,
    extra_instructions: str = "",
) -> str:
    """게시글/프로필 기반 동적 tail(자원 상황 + 입력)을 생성한다.

    제목·베스트 댓글·추가 지시는 게시글마다 달라지는 동적 요소이므로 user tail에만 둔다
    (system 캐시 prefix를 바이트 동일하게 유지하기 위함).
    """
    guide = _STRATEGY_GUIDE.get(profile.strategy, "")
    parts = [
        "## 자원 상황\n"
        f"- 이미지: {profile.image_count}장 / 예상 문장: {profile.estimated_sentences}개\n"
        f"- 전략: {profile.strategy} — {guide}\n",
        "## 입력\n"
        + (f"- 제목: {title}\n" if title else "")
        + f"- 본문: {post_content[:4000]}\n",
    ]
    if best_comments:
        comment_lines = "\n".join(f"- {c}" for c in best_comments)
        parts.append(f"## 베스트 댓글\n{comment_lines}\n")
    if extra_instructions:
        parts.append(f"## 추가 지시사항\n{extra_instructions}\n")
    return "\n".join(parts)


def create_chunking_prompt(
    post_content: str,
    profile: ResourceProfile,
    *,
    extended: bool = False,
    title: str = "",
    best_comments: list[str] | None = None,
    extra_instructions: str = "",
) -> str:
    """정적 prefix + 동적 tail을 합친 전체 청킹 프롬프트를 반환한다.

    실제 LLM 호출은 chunk_with_llm()에서 system/user를 분리해 보내지만,
    로깅·테스트 호환을 위해 이 함수는 합본 문자열을 그대로 제공한다.

    Args:
        extended: True이면 title_suggestion/tags/mood 필드도 출력 형식에 포함한다.
        title: 게시글 제목 (후킹 재료)
        best_comments: 베스트 댓글 ("닉네임: 내용" 형식) 목록
        extra_instructions: 성과 피드백·A/B 변형 추가 지시
    """
    return (
        build_chunking_system(extended=extended)
        + "\n\n"
        + _build_chunking_user(
            post_content,
            profile,
            title=title,
            best_comments=best_comments,
            extra_instructions=extra_instructions,
        )
    )


def _call_llm_json_sync(user_prompt: str, system: str, model: str) -> dict:
    return call_llm_json(
        user_prompt,
        model=model,
        call_type="chunk",
        timeout=180,
        system=system,
        cache_prefix=True,
        temperature=0.7,  # 창의적 구어체 (레거시 generate_script와 동일값)
    )


async def chunk_with_llm(
    post_content: str,
    profile: ResourceProfile,
    *,
    post_id: int | None = None,
    extended: bool = False,
    title: str = "",
    best_comments: list[str] | None = None,
    extra_instructions: str = "",
) -> dict:
    """ResourceProfile 기반 LLM 청킹을 수행하고 raw 대본 dict를 반환한다.

    Args:
        post_content: 게시글 본문
        profile:      Phase 1에서 생성된 ResourceProfile
        post_id:      LLM 로그 연결용 게시글 ID (선택)
        extended:     True이면 title_suggestion/tags/mood 추가 필드도 반환
        title:        게시글 제목 (후킹·title_suggestion 재료)
        best_comments: 베스트 댓글 ("닉네임: 내용" 형식) — type=comment 씬 인용 재료
        extra_instructions: 성과 피드백·A/B 변형 추가 지시

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
    user = _build_chunking_user(
        post_content,
        profile,
        title=title,
        best_comments=best_comments,
        extra_instructions=extra_instructions,
    )
    # 로그 완전성을 위해 합본 프롬프트를 별도로 보관
    prompt = create_chunking_prompt(
        post_content,
        profile,
        extended=extended,
        title=title,
        best_comments=best_comments,
        extra_instructions=extra_instructions,
    )
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

    # LLM이 JSON을 반환하지 않은 경우 (콘텐츠 거부 또는 파싱 불가)
    if not result:
        from ai_worker.llm.transport import LLMContentRefusalError
        raise LLMContentRefusalError(
            "LLM이 유효한 JSON 대본을 반환하지 않음 — 콘텐츠 거부 또는 응답 파싱 실패"
        )

    # 필수 키 검증
    for key in ("hook", "body", "closer"):
        if key not in result:
            raise ValueError(f"LLM 응답에 필수 키 누락: '{key}' | 응답={result}")

    if not isinstance(result["body"], list):
        result["body"] = [str(result["body"])]

    # 선택 필드 기본값 보정 (extended=True 시 전체, False 시 mood만 보장)
    result.setdefault("mood", "daily")
    if extended:
        result.setdefault("title_suggestion", "")
        result.setdefault("tags", [])
        if not isinstance(result["tags"], list):
            result["tags"] = []

    logger.info(
        "LLM 청킹 완료: hook=%d자, body=%d문장, closer=%d자 (%dms)",
        len(result["hook"]), len(result["body"]), len(result["closer"]), timer.elapsed_ms,
    )
    return result
