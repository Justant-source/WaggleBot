package com.wagglebot.config;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;

/**
 * 외부 연동 엔드포인트({@code /api/external/**}) 전용 인증 필터.
 *
 * Again Spring 등 외부 서비스가 X-Api-Key 헤더로 인증한다.
 * 값은 EXTERNAL_API_KEY 환경변수(또는 app.external.api-key) — 로컬 기본값 "change-me-external".
 * 그 외 경로는 그대로 통과시킨다 (기존 크롤러/수신함/에디터 흐름에 영향 없음).
 */
@Component
@Slf4j
public class ExternalApiKeyFilter extends OncePerRequestFilter {

    private static final String EXTERNAL_PATH_PREFIX = "/api/external/";
    private static final String API_KEY_HEADER = "X-Api-Key";

    @Value("${app.external.api-key:change-me-external}")
    private String expectedApiKey;

    @Override
    protected void doFilterInternal(
        HttpServletRequest request, HttpServletResponse response, FilterChain filterChain
    ) throws ServletException, IOException {
        if (!request.getRequestURI().startsWith(EXTERNAL_PATH_PREFIX)) {
            filterChain.doFilter(request, response);
            return;
        }

        String provided = request.getHeader(API_KEY_HEADER);
        if (provided == null || !provided.equals(expectedApiKey)) {
            log.warn("[external] X-Api-Key 인증 실패: path={} remote={}", request.getRequestURI(), request.getRemoteAddr());
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json");
            response.getWriter().write("{\"error\":\"invalid or missing X-Api-Key\",\"status\":401}");
            return;
        }
        filterChain.doFilter(request, response);
    }
}
