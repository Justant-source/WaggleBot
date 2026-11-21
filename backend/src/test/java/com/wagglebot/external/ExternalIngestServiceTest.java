package com.wagglebot.external;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wagglebot.domain.CommentRepository;
import com.wagglebot.domain.Content;
import com.wagglebot.domain.ContentRepository;
import com.wagglebot.domain.Post;
import com.wagglebot.domain.PostRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/** 포맷 실험 옵션(commentCount/outroMode/formatArm/empathyRatio) → variant_config 전달 검증. */
class ExternalIngestServiceTest {

    private final ObjectMapper mapper = new ObjectMapper();
    private PostRepository postRepo;
    private ContentRepository contentRepo;
    private ExternalIngestService service;

    @BeforeEach
    void setUp() {
        postRepo = mock(PostRepository.class);
        CommentRepository commentRepo = mock(CommentRepository.class);
        contentRepo = mock(ContentRepository.class);
        when(postRepo.findBySiteCodeAndOriginId(any(), any())).thenReturn(Optional.empty());
        when(postRepo.save(any(Post.class))).thenAnswer(inv -> {
            Post p = inv.getArgument(0);
            p.setId(7L);
            return p;
        });
        when(contentRepo.findByPostId(any())).thenReturn(Optional.empty());
        service = new ExternalIngestService(postRepo, commentRepo, contentRepo, mapper);
    }

    private JsonNode ingest(ExternalJobRequest.OptionsInput options, Boolean paired) {
        service.ingest(new ExternalJobRequest("again_spring", "ext-1", "제목", "본문", null, paired, options));
        ArgumentCaptor<Content> cap = ArgumentCaptor.forClass(Content.class);
        verify(contentRepo).save(cap.capture());
        return cap.getValue().getVariantConfig();
    }

    private ExternalJobRequest.OptionsInput opts(Integer commentCount, String outroMode, String formatArm, JsonNode ratio) {
        return new ExternalJobRequest.OptionsInput(
            null, null, null, null, null, null, null, null, null, null, null, null, null, null, null,
            commentCount, outroMode, formatArm, ratio);
    }

    @Test
    void absentKeysAreNotWritten() {
        JsonNode cfg = ingest(opts(null, null, null, null), true);
        assertThat(cfg.has("comment_count")).isFalse();
        assertThat(cfg.has("outro_mode")).isFalse();
        assertThat(cfg.has("format_arm")).isFalse();
        assertThat(cfg.has("empathy_ratio")).isFalse();
    }

    @Test
    void experimentKeysPassThrough() throws Exception {
        JsonNode ratio = mapper.readTree("{\"a\":64,\"b\":36}");
        JsonNode cfg = ingest(opts(0, "vote_reveal", "short_reveal", ratio), true);
        assertThat(cfg.get("comment_count").asInt()).isEqualTo(0);
        assertThat(cfg.get("outro_mode").asText()).isEqualTo("vote_reveal");
        assertThat(cfg.get("format_arm").asText()).isEqualTo("short_reveal");
        assertThat(cfg.get("empathy_ratio").get("a").asInt()).isEqualTo(64);
        assertThat(cfg.get("empathy_ratio").get("b").asInt()).isEqualTo(36);
        // outro_text 결정 로직은 그대로 — 문구는 워커가 정한다
        assertThat(cfg.get("outro_text").asText()).isEqualTo("상대방의 사연도 궁금하시죠? 댓글에서 확인해 보세요.");
    }

    @Test
    void ratioIgnoredUnlessVoteReveal() throws Exception {
        JsonNode ratio = mapper.readTree("{\"a\":64,\"b\":36}");
        JsonNode cfg = ingest(opts(2, "partner_cta", null, ratio), false);
        assertThat(cfg.get("comment_count").asInt()).isEqualTo(2);
        assertThat(cfg.has("empathy_ratio")).isFalse();
    }

    @Test
    void malformedRatioDropped() throws Exception {
        JsonNode ratio = mapper.readTree("{\"a\":\"x\",\"b\":36}");
        JsonNode cfg = ingest(opts(null, "vote_reveal", null, ratio), true);
        assertThat(cfg.has("empathy_ratio")).isFalse();
    }
}
