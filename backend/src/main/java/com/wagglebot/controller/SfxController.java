package com.wagglebot.controller;

import com.wagglebot.settings.SfxCatalogService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/sfx")
@RequiredArgsConstructor
@Slf4j
public class SfxController {

    private final SfxCatalogService sfxCatalogService;

    /**
     * GET /api/sfx/mapping
     * 현재 SFX 설정 + 라이브러리 반환
     */
    @GetMapping("/mapping")
    public ResponseEntity<Map<String, Object>> getSfxMapping() {
        try {
            Map<String, Object> mapping = sfxCatalogService.loadSfxMapping();
            return ResponseEntity.ok(mapping);
        } catch (Exception e) {
            log.error("SFX 매핑 로드 실패", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("error", "SFX 매핑 로드 실패: " + e.getMessage()));
        }
    }

    /**
     * PUT /api/sfx/mapping
     * SFX 설정 업데이트
     * Request: { "events": [...], "maxPerVideo": 40 }
     */
    @PutMapping("/mapping")
    public ResponseEntity<?> updateSfxMapping(@RequestBody Map<String, Object> request) {
        try {
            // 입력 검증
            if (request == null || request.get("events") == null) {
                return ResponseEntity.badRequest()
                    .body(Map.of("error", "events 필드 필수"));
            }

            // 업데이트
            Map<String, Object> result = sfxCatalogService.updateSfxMapping(request);
            return ResponseEntity.ok(result);
        } catch (IllegalArgumentException e) {
            log.warn("SFX 매핑 검증 실패: {}", e.getMessage());
            return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(Map.of("error", e.getMessage()));
        } catch (IOException e) {
            log.error("SFX 매핑 저장 실패", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("error", "저장 실패: " + e.getMessage()));
        } catch (Exception e) {
            log.error("SFX 매핑 업데이트 실패", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(Map.of("error", "처리 실패: " + e.getMessage()));
        }
    }
}
