# ADR-0008: TTS 텍스트 정규화 표준을 Flight-Brain 기준(소수점 `쩜`)으로 통일

> **status:** accepted (코드 완료, 프로필 운영 활성화·청취 확인 미실시 — 2026-11-27)
> **date:** 2026-11-27
> **related:** worker/ai_worker/tts/prenorm.py, config/tts_profile/shorts-ko.yaml, worker/tools/sync_tts_profile.py, worker/ai_worker/tts/synth.py, worker/test/test_tts_normalizer.py

## 컨텍스트

WaggleBot의 `normalizer.py`·`number_reader.py`(soynlp 포함)는 Flight-Brain 정규화를 복사한 뒤 분기한 코드였다(소수점 `점` vs `쩜`, 발음 교정 사전은 2026-03-08 비활성). 두 앱이 같은 규칙을 따로 유지했고 서로 출력이 달랐다. Local-TTS는 Flight-Brain 정규화 코드를 이식해 서버 내장 정규화로 제공한다.

## 결정

1. **정규화 표준은 Flight-Brain 기준으로 통일**한다(확정 D18). 소수점은 `쩜`(`3.5` → `삼 쩜 오`).
2. **3분담**으로 구 로컬 정규화를 대체한다. 구 `normalizer.py`·`number_reader.py`·soynlp 의존 경로는 삭제.
   - **서버 내장:** 숫자·콤마·전화·월(유월/시월)·범위·퍼센트·소수·도량형·카운터·말줄임·따옴표·특수문자·공백·문단 보존·종결부호·조사 교정(`josa_fix`).
   - **발음 프로필 `wagglebot/shorts-ko` v1**(39 엔트리, 골든 27): 슬랭(남친·여친·베댓·갑분싸·시모·장모·솔까말·킹받·억까·N잡·U턴), `keep 장모님`, 영문 약어 27종(`5G` 포함). 원본 `config/tts_profile/shorts-ko.yaml`, 업로드·검증·미리보기·활성화는 `worker/tools/sync_tts_profile.py`. 프로필 키 네임스페이스는 client id(`wagglebot`)와 같아야 한다.
   - **앱 `prenorm.py`:** 프로필로 표현할 수 없는 규칙만 — 화자 접두어(`ㅇㅇ:`) 제거, URL·이메일·해시태그 삭제, 자모 슬랭(`ㄹㅇ`→진짜 등)·`ㄷㄷ`·단독 자모·`^` 삭제(`ㅋㅋ/ㅎㅎ` 웃음 마커 폐기), `N대`(`A~B대` 포함)·`N기`를 한자어 수사로 선변환(서버가 고유어 `쉰 대`·`네 기`로 읽어 연령대·단계 의미가 틀어지는 것을 방지). 문단 구분(빈 줄)은 서버 청커 경계라 보존.
3. 앱은 서버 응답에 의존해 청크를 나누지 않는다. 서버 `chunk max_chars 120`을 쓰고 로컬 분할은 없다. 전처리 후 읽을 글자가 없으면 요청하지 않고 `ValueError`로 종료한다.

## 근거

- **L1 diff 측정(2026-11-27):** 구 `normalize_for_tts` 출력 대 신 경로(`prenormalize` + 서버 `jobs:dry_run`, 프로필 활성 상태) 1726건(DB 대본 1148 + 케이스 578). 일치 1262, 차이 464, 차이 hunk 685개 전부 분류에 포함, **비의도 회귀 0**. 주요 차이는 말미 쉼표→마침표(서버 종결부호 보정), 서버 단위 띄어쓰기, 소수점 `점`→`쩜`(9건), 영문 약어 낱자·기호 읽기, 그리고 구 버그 수정(`장모님님`, 조사 보정, 고유어 20→`스무`, `세`=한자어, `일만`→`만`, soynlp 부작용). 상세 분류표는 Flight-Brain `.temp/local_tts/12_wb_norm_diff.md`.
- 규칙을 서버 한 곳에 두면 두 앱의 발음이 일치하고, 앱별 차이는 프로필(데이터)로만 표현된다.

## 영향·후속

- 출력 문구가 바뀌므로 **청취 비교 전에는 최종 품질 보증이 아니다.** 프로필 활성화(`--activate`)는 운영 반영 단계에서 명시적으로만 한다.
- 서버는 빈 텍스트에 `400`을 반환하므로 호출처는 전처리 결과가 공백이면 합성을 생략한다(현재 `synth.synthesize`가 `ValueError`).
- 프로필에 없는 영문 약어(LG·MBC·KBS·SUV 등)는 서버가 낱자로 읽는다(이전엔 원문 유지). 필요 시 프로필에 추가한다.
- 서버의 `대`·`기` 카운터를 고유어로 읽는 동작은 Local-TTS 쪽 확인 권고 항목이다(prenorm 보정으로 우회 중).
- `to_narration_text`의 연결어미 쉼표 이어 읽기 규칙은 Fish 프로소디용이라 후속에 폐기 가능하다.
