-- 010 / V5: contents.tts_voice 의 구 키(Fish 참조 음성)를 Supertonic 프리셋(M1~M5, F1~F5)으로 이관.
-- 성별 보존. 같은 성별 안에서는 (post_id + 구 키 서수) % 5 로 분산(결정적).
-- 런타임 resolve_voice()는 구 키도 처리하므로 이 이관은 표시·통계 일관성용이며 멱등이다.
-- 대상: contents.tts_voice, contents.variant_config.$.tts_voice (comment_voices는 JSON 구조가 가변이라 런타임 resolver에 위임).
-- 이미 프리셋(M1~F5)인 값은 변경하지 않는다. 매핑 불가한 비어있지 않은 값은 NULL(=전역 기본/자동 선택).
-- 적용 전 백업 권장: contents_tts_voice_bak 테이블에 id, tts_voice, variant_config 복사.
-- 주의: worker runner.py는 세미콜론으로 문장을 나누므로 주석에 세미콜론을 쓰지 않는다.

CREATE TEMPORARY TABLE IF NOT EXISTS tmp_legacy_voice_map (
    legacy_key VARCHAR(64) PRIMARY KEY,
    gender CHAR(1) NOT NULL,
    ordinal INT NOT NULL
);
DELETE FROM tmp_legacy_voice_map;
INSERT INTO tmp_legacy_voice_map (legacy_key, gender, ordinal) VALUES
    ('typecast_ref_v2', 'M', 0),
    ('kangil_ref', 'M', 1),
    ('typecast_ref', 'M', 2),
    ('default', 'M', 3),
    ('yohan', 'M', 4),
    ('manbo', 'M', 5),
    ('manu', 'M', 6),
    ('host_m', 'M', 7),
    ('christian', 'M', 8),
    ('deep_lax', 'M', 9),
    ('krishna', 'M', 10),
    ('miguel', 'M', 11),
    ('min_jun', 'M', 12),
    ('theo', 'M', 13),
    ('yohan_koo', 'M', 14),
    ('ko-kr-injoonneural', 'M', 15),
    ('ko-kr-hyunsuneural', 'M', 16),
    ('ko-kr-bongjinneural', 'M', 17),
    ('ko-kr-gookminneural', 'M', 18),
    ('seohyeon_ref', 'F', 0),
    ('kyunghwa_ref', 'F', 1),
    ('yura', 'F', 2),
    ('host_f', 'F', 3),
    ('hyoeun_ref', 'F', 4),
    ('anna', 'F', 5),
    ('krys', 'F', 6),
    ('sunny', 'F', 7),
    ('anna_kim', 'F', 8),
    ('blondie', 'F', 9),
    ('callie', 'F', 10),
    ('han', 'F', 11),
    ('hope', 'F', 12),
    ('ivanna', 'F', 13),
    ('lucy', 'F', 14),
    ('norah', 'F', 15),
    ('tara', 'F', 16),
    ('ko-kr-sunhineural', 'F', 17);

UPDATE contents c
JOIN tmp_legacy_voice_map m ON m.legacy_key = LOWER(c.tts_voice)
SET c.tts_voice = CONCAT(m.gender, 1 + MOD(c.post_id + m.ordinal, 5));

UPDATE contents
SET tts_voice = NULL
WHERE tts_voice IS NOT NULL
  AND tts_voice <> ''
  AND UPPER(tts_voice) NOT IN ('M1','M2','M3','M4','M5','F1','F2','F3','F4','F5');

UPDATE contents
SET tts_voice = NULL
WHERE tts_voice = '';

UPDATE contents c
JOIN tmp_legacy_voice_map m ON m.legacy_key = LOWER(JSON_UNQUOTE(JSON_EXTRACT(c.variant_config, '$.tts_voice')))
SET c.variant_config = JSON_SET(c.variant_config, '$.tts_voice', CONCAT(m.gender, 1 + MOD(c.post_id + m.ordinal, 5)))
WHERE JSON_VALID(c.variant_config) AND JSON_EXTRACT(c.variant_config, '$.tts_voice') IS NOT NULL;

DROP TEMPORARY TABLE IF EXISTS tmp_legacy_voice_map;
