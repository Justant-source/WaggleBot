package com.wagglebot.external;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * Mirrors Again-Spring's MarketingBriefTextTest (commit 732491a9) — real CRLF, literal
 * backslash-n/backslash-r, Won-sign-n/Won-sign-r, and legacy JSON backslash-u escapes
 * must all collapse to a real newline.
 */
class ExternalTextNormalizerTest {

    @Test
    void nullPassesThrough() {
        assertThat(ExternalTextNormalizer.normalize(null)).isNull();
    }

    @Test
    void plainTextUnchanged() {
        assertThat(ExternalTextNormalizer.normalize("평범한 한 줄 텍스트")).isEqualTo("평범한 한 줄 텍스트");
    }

    @Test
    void realNewlinePreserved() {
        assertThat(ExternalTextNormalizer.normalize("첫 줄\n둘째 줄")).isEqualTo("첫 줄\n둘째 줄");
    }

    @Test
    void crlfCollapsesToLf() {
        assertThat(ExternalTextNormalizer.normalize("첫 줄\r\n둘째 줄")).isEqualTo("첫 줄\n둘째 줄");
    }

    @Test
    void literalBackslashNBecomesRealNewline() {
        assertThat(ExternalTextNormalizer.normalize("첫 줄\\n둘째 줄")).isEqualTo("첫 줄\n둘째 줄");
    }

    @Test
    void literalBackslashRBackslashNBecomesSingleNewline() {
        assertThat(ExternalTextNormalizer.normalize("첫 줄\\r\\n둘째 줄")).isEqualTo("첫 줄\n둘째 줄");
    }

    @Test
    void wonSignNBecomesRealNewline() {
        assertThat(ExternalTextNormalizer.normalize("첫 줄₩n둘째 줄")).isEqualTo("첫 줄\n둘째 줄");
    }

    @Test
    void wonSignRWonSignNBecomesSingleNewline() {
        assertThat(ExternalTextNormalizer.normalize("첫 줄₩r₩n둘째 줄")).isEqualTo("첫 줄\n둘째 줄");
    }

    @Test
    void unicodeEscapeDecodes() {
        assertThat(ExternalTextNormalizer.normalize("첫 줄\\u000A둘째 줄")).isEqualTo("첫 줄\n둘째 줄");
    }

    @Test
    void wonCurrencyAmountPreserved() {
        // ₩ not followed by n/r is a currency amount, not a line-break artifact.
        assertThat(ExternalTextNormalizer.normalize("월세 ₩500,000을 아직도 안 줬음"))
            .isEqualTo("월세 ₩500,000을 아직도 안 줬음");
    }
}
