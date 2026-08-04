package com.wagglebot.external;

import java.util.List;

/**
 * POST /api/external/jobs 요청 바디.
 *
 * 외부 서비스(Again Spring 등)가 사연 하나를 WaggleBot 파이프라인에 밀어넣기 위한 계약.
 */
public record ExternalJobRequest(
    String source,
    String externalId,
    String title,
    String body,
    List<CommentInput> comments,
    Boolean paired,
    OptionsInput options
) {
    public record CommentInput(String author, String body, Integer likeCount) {}

    public record OptionsInput(Boolean videoGen, Boolean autoHdRender) {}
}
