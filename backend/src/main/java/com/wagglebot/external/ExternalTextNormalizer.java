package com.wagglebot.external;

import java.util.regex.Pattern;

/**
 * Canonical line-break normalization for text arriving through the external ingest
 * boundary (title/body from Again-Spring via ASM). Mirrors Again-Spring's
 * {@code MarketingBriefText.normalize()} (commit 732491a9) so the same escape artifact
 * never reaches a rendered thumbnail/subtitle regardless of which hop it slipped through.
 *
 * <p>In the normal AS → ASM → WaggleBot path, ASM's {@code StoryBrief} pydantic validators
 * already normalize this text before it's sent here, so this is a defense-in-depth layer
 * for any other caller of {@code POST /api/external/jobs} — matching this codebase's
 * established multi-layer defense pattern for content-safety issues (2026-08-16).
 *
 * <p>Handles: real CRLF/lone CR, literal two-character backslash-n/backslash-r, Won-sign-n
 * /Won-sign-r (a Korean keyboard's backslash key types the Won sign, so the same
 * literal-escape bug reproduces with ₩ instead of \), and legacy JSON backslash-u escapes.
 * Does not touch unrelated backslash/₩ characters (e.g. a ₩ amount in story text) — only
 * the specific run-of-escapes-before-r/n pattern is replaced.
 */
public final class ExternalTextNormalizer {

    private static final Pattern UNICODE_ESCAPE = Pattern.compile("\\\\+u[0-9a-fA-F]{4}");
    private static final Pattern CRLF_RUN = Pattern.compile("\\\\+r\\\\+n");
    private static final Pattern WON_CRLF_RUN = Pattern.compile("₩+r₩+n");
    private static final Pattern LF_RUN = Pattern.compile("\\\\+n");
    private static final Pattern WON_LF_RUN = Pattern.compile("₩+n");
    private static final Pattern CR_RUN = Pattern.compile("\\\\+r");
    private static final Pattern WON_CR_RUN = Pattern.compile("₩+r");

    private ExternalTextNormalizer() {
    }

    public static String normalize(String value) {
        if (value == null) {
            return null;
        }
        String s = value;
        s = s.replace("\r\n", "\n").replace('\r', '\n');
        s = CRLF_RUN.matcher(s).replaceAll("\n");
        s = WON_CRLF_RUN.matcher(s).replaceAll("\n");
        s = LF_RUN.matcher(s).replaceAll("\n");
        s = WON_LF_RUN.matcher(s).replaceAll("\n");
        s = CR_RUN.matcher(s).replaceAll("\n");
        s = WON_CR_RUN.matcher(s).replaceAll("\n");
        if (UNICODE_ESCAPE.matcher(s).find()) {
            s = decodeUnicodeEscapes(s);
        }
        return s;
    }

    private static String decodeUnicodeEscapes(String value) {
        StringBuilder normalized = new StringBuilder(value.length());
        int index = 0;
        while (index < value.length()) {
            char character = value.charAt(index);
            if (character == '\\' && index + 5 < value.length() && value.charAt(index + 1) == 'u'
                && isHex(value, index + 2, index + 6)) {
                normalized.append((char) Integer.parseInt(value.substring(index + 2, index + 6), 16));
                index += 6;
            } else {
                normalized.append(character);
                index++;
            }
        }
        return normalized.toString();
    }

    private static boolean isHex(String value, int startInclusive, int endExclusive) {
        for (int index = startInclusive; index < endExclusive; index++) {
            if (Character.digit(value.charAt(index), 16) < 0) {
                return false;
            }
        }
        return true;
    }
}
