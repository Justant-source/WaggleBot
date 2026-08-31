package com.wagglebot.external;

import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.List;
import java.time.OffsetDateTime;

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

    public record OptionsInput(
        Boolean videoGen,
        Boolean autoHdRender,
        String ttsVoice,
        /**
         * Deprecated for video path — ignored at ingest (metaphor PNG unplugged).
         * Kept for backward-compatible JSON deserialization.
         */
        String metaphorId,
        String commentVoices,
        /** Again Spring hook_emotion mapped mood (scene_policy key). */
        String mood,
        /** Fish Speech / OpenAudio tts_emotion marker key for intro. */
        String ttsEmotion,
        /** Soft video length target seconds (Reels 30 / Shorts 45). */
        Integer maxDurationSec,
        /** Layout profile hint: reels_compact | shorts_standard. */
        String platformLayout,
        /** Queue/SLA controls for time-sensitive external marketing content. */
        String priority,
        OffsetDateTime deadlineAt,
        Boolean preScripted,
        String renderProfile,
        /**
         * Channel-specific Sibomi insertion plan (role/image_id/caption/beat_index/size/dwell).
         * Accepts camelCase {@code sibomPlan} or snake_case {@code sibom_plan}.
         */
        @JsonAlias("sibom_plan")
        JsonNode sibomPlan
    ) {}
}
