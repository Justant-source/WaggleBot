package com.wagglebot.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

import java.util.Arrays;
import java.util.List;

@Configuration
public class CorsConfig {

    /**
     * 허용 Origin 패턴(CSV). 기본 "*" — 내부망/Tailscale에서 임의 IP·호스트로 접속하는
     * 어드민 도구 특성상 Origin을 화이트리스트로 고정하면 IP가 바뀔 때마다 403이 난다.
     * (Next.js 프록시가 브라우저 Origin을 백엔드로 전달하므로 프록시 경유라도 CORS 검사 대상.)
     * 보안이 필요한 배포는 app.cors-allowed-origins로 구체 Origin을 지정해 제한할 것.
     * allowCredentials=true 와 함께 쓰려면 setAllowedOrigins("*")는 불가 →
     * setAllowedOriginPatterns 사용(매칭된 실제 Origin을 응답에 반사).
     */
    @Value("${app.cors-allowed-origins:*}")
    private String allowedOriginPatterns;

    @Bean
    public CorsFilter corsFilter() {
        List<String> patterns = Arrays.stream(allowedOriginPatterns.split(","))
                .map(String::trim)
                .filter(s -> !s.isEmpty())
                .toList();

        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOriginPatterns(patterns);
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"));
        config.setAllowedHeaders(List.of("*"));
        config.setAllowCredentials(true);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        return new CorsFilter(source);
    }
}
