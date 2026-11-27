# ADR-0007: 보이스를 Supertonic 프리셋(M1~M5·F1~F5)으로 전환

> **status:** accepted (코드 완료, DB 마이그레이션 미적용 — 2026-11-27)
> **date:** 2026-11-27
> **related:** config/voices.json, worker/ai_worker/tts/voice_resolver.py, worker/db/migrations/010_tts_voice_presets.sql, backend/src/main/resources/db/migration/V5__tts_voice_presets.sql, backend/src/main/java/com/wagglebot/settings/VoiceCatalogService.java, config/pipeline.json

## 컨텍스트

Fish Speech 시절 보이스는 참조 음성(`assets/voices/<key>/NN.wav+NN.lab`)으로 클로닝하는 24개 키(`seohyeon_ref`·`kangil_ref`·`typecast_ref_v2`·`yura`·`yohan` 등)였다. Local-TTS(Supertonic)는 클로닝 없이 프리셋 보이스를 제공한다([ADR-0006](0006-local-tts-provider.md)). 기존 DB(`contents.tts_voice`, `variant_config`)·`pipeline.json`·`scene/settings.yaml`에는 구 키가 이미 저장돼 있다.

## 결정

1. **보이스는 프리셋 10종:** 남 `M1~M5`, 여 `F1~F5`(`config/voices.json` v4, `engine: supertonic`, 필드 `key·label·gender·engine`). 클로닝은 포기한다.
2. **해석은 `voice_resolver.resolve_voice(voice_key, post_id)` 한 곳**에서 한다. 항상 `M1..F5` 중 하나를 돌려주고 같은 입력이면 같은 결과(결정적).
   - 프리셋 키(대소문자 무관) → 그대로.
   - 구 키 → **성별 보존**. `random.Random(post_id)`로 같은 성별 프리셋 5개를 섞은 순열에서 구 키의 고정 서수(목록 순서 `_LEGACY_MALE/_LEGACY_FEMALE`)로 고른다. 같은 글의 서로 다른 구 키가 가능한 한 다른 프리셋이 된다. 서수 순서를 바꾸면 기존 글의 보이스가 바뀌므로 목록 끝에만 추가한다.
   - 없음·빈 값·미지 키 → `post_id` 시드로 전체 10종에서 결정적 랜덤(`post_id`도 없으면 `F1`).
   - 키 `default`는 구 키 목록(남성 서수 3)이라 남성 프리셋으로 해석된다.
3. **DB 이관은 표시·통계 일관성용이며 멱등이다.** `010_tts_voice_presets.sql`(worker runner, 수동 실행)과 `V5__tts_voice_presets.sql`(Flyway, backend 기동 시 자동)은 동일 SQL로 `contents.tts_voice`·`variant_config.$.tts_voice`를 `(post_id + 서수) % 5` 규칙으로 변환하고 매핑 불가 값은 NULL로 둔다. 런타임 resolver가 구 키를 처리하므로 **마이그레이션이 없어도 동작은 같다.**
4. **기본값:** `pipeline.json` `tts_engine=local-tts`, `tts_voice=default`, `comment_voices=["M2","F2","M3"]`, `scene/settings.yaml` 댓글 화자 author `M2`·partner `F2`·neutral `default`. backend 기본 `tts_voice=F1`.
5. **샘플:** 프리셋별 `voice_preview_<KEY>.mp3`를 사전 생성(`assets/voices/`), backend `GET /api/tts/voices/{key}/sample`이 스트리밍한다.
6. **캐시:** 디스크 TTS 캐시 키는 요청 키가 아니라 해석된 프리셋을 쓴다(`pp_v7`).

## 근거

- 프리셋은 서버가 보증하는 보이스라 참조 음성 품질·언어 회귀(중국어) 문제와 `assets/voices` UID 1000 권한 요구가 사라진다.
- post_id 시드는 재처리·재큐 때도 같은 글이 같은 보이스를 유지하게 한다. 성별 보존은 화자 성별이 맞는 최소 보장이다.
- resolver를 런타임 SSOT로 두면 마이그레이션 적용 순서·롤링 배포에 의존하지 않는다.

## 영향·알려진 한계

- 구 참조 음성 폴더(`assets/voices/<구 키>/`)는 합성에 쓰이지 않는다. 정리는 별도 승인 후 진행한다(백업 먼저).
- `script/voice_assigner.pick_voice`는 `age_range`가 있는 후보만 고르는데 v4 항목에는 `age_range`가 없어 항상 `VOICE_DEFAULT`(→ 남성 프리셋)를 반환한다. 성별·연령 자동 배정은 사실상 비활성이며 후속 확인 대상이다.
- 마이그레이션은 운영 DB에 적용하지 않았다. backend 재시작 시 Flyway V5가 자동 적용되므로 적용 시점은 backend 재배포로 결정된다(적용 전 `contents_tts_voice_bak` 백업 권장).
- 프리셋 5+5 보이스의 청취 비교·최종 선정은 미실시.
