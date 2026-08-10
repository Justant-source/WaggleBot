package com.wagglebot.external;

import java.time.Instant;
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
    OptionsInput options,
    String category,
    Integer viewCount
) {
    /**
     * 댓글 씬(Again Spring Shorts)용 입력. 화면 최대 3개까지만 사용된다
     * ({@link com.wagglebot.external.ExternalIngestService} 참고).
     *
     * @param author    표시용 닉네임 (구버전 호환 — nickname 미지정 시 이 값을 그대로 사용)
     * @param nickname  표시용 닉네임 명시 필드. 지정되면 author보다 우선한다.
     * @param authorId  원본/해시 사용자 ID — 분석용 보관만, 화면 표시에는 절대 쓰지 않는다.
     * @param body      댓글 본문
     * @param likeCount 추천수
     * @param createdAt 댓글 작성 시각 (없으면 ingest 시각으로 대체)
     * @param side      "author" | "partner" | "neutral" — 진영색 스타일용. 미지정/무효값 → "neutral"
     */
    public record CommentInput(
        String author,
        String nickname,
        String authorId,
        String body,
        Integer likeCount,
        Instant createdAt,
        String side
    ) {
        /** 화면에 표시할 닉네임. nickname이 있으면 우선, 없으면 author. authorId는 절대 표시하지 않는다. */
        public String displayAuthor() {
            return (nickname != null && !nickname.isBlank()) ? nickname : author;
        }
    }

    public record OptionsInput(Boolean videoGen, Boolean autoHdRender, String ttsVoice, String metaphorId, List<String> metaphorIds, String commentVoices) {}
}
