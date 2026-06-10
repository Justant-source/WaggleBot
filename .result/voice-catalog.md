# voice-catalog

## 1. 작업 결과

`VoiceCatalogService`의 JSON 파싱 버그 2건 수정.
`voices.json`과 `prompt_presets.json`이 `{"voices": [...]}` / `{"presets": [...]}` 래퍼 구조인데
Java에서 직접 `List<Map>` 으로 파싱 시도해 `InvalidDefinitionException` 발생 → 빈 리스트 반환.

## 2. 수정 내용

### VoiceCatalogService.java

**loadVoices()**
```java
// 수정 전: 직접 List로 파싱 — 구조 불일치로 항상 실패
List<Map<String, Object>> voices = MAPPER.readValue(json, LIST_REF);

// 수정 후: 래퍼 객체에서 "voices" 배열 추출
Map<String, Object> root = MAPPER.readValue(json, new TypeReference<Map<String, Object>>() {});
List<Map<String, Object>> voices = (List<Map<String, Object>>) root.getOrDefault("voices", new ArrayList<>());
```

**getPromptPresets()**
```java
// 수정 전: 직접 List로 파싱 — 구조 불일치
return MAPPER.readValue(json, STR_LIST_REF);

// 수정 후:
Map<String, Object> root = MAPPER.readValue(json, new TypeReference<Map<String, Object>>() {});
List<Map<String, String>> presets = (List<Map<String, String>>) root.getOrDefault("presets", new ArrayList<>());
return presets;
```

불필요해진 `LIST_REF` / `STR_LIST_REF` 상수 제거.

## 3. 영향

- `GET /api/tts/voices` → 보이스 목록 정상 반환 (기존: 항상 빈 리스트)
- `GET /api/editor/prompt-presets` → 프리셋 목록 정상 반환 (기존: 항상 빈 리스트)
- VoicePicker, PromptPresetPanel 컴포넌트가 실제 데이터를 표시

## 4. 수동 테스트 방법

```
1. backend 재시작 → GET /api/tts/voices → voices 배열 8개 반환 확인
2. GET /api/editor/prompt-presets → presets 배열 반환 확인
3. 에디터 페이지 → VoicePicker 보이스 카드 표시 확인
4. 에디터 페이지 → PromptPresetPanel 프리셋 버튼 표시 확인
```

## 5. 추천 commit message

```
fix: VoiceCatalogService voices.json / prompt_presets.json 파싱 버그 수정
```
