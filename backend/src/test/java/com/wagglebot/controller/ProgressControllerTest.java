package com.wagglebot.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wagglebot.common.PostStatus;
import com.wagglebot.domain.Content;
import com.wagglebot.domain.ContentRepository;
import com.wagglebot.domain.ContentRuntimeState;
import com.wagglebot.domain.ContentRuntimeStateRepository;
import com.wagglebot.domain.Post;
import com.wagglebot.domain.PostRepository;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.data.jpa.domain.Specification;

import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

/** /api/progress 의 processing[].progress 는 content_runtime_state(progress)를 정본으로 노출한다. */
class ProgressControllerTest {

    private final ObjectMapper om = new ObjectMapper();

    @SuppressWarnings({"unchecked", "rawtypes"})
    private Map<String, Object> firstProcessing(Content content, Optional<ContentRuntimeState> state) {
        PostRepository postRepo = Mockito.mock(PostRepository.class);
        ContentRepository contentRepo = Mockito.mock(ContentRepository.class);
        ContentRuntimeStateRepository stateRepo = Mockito.mock(ContentRuntimeStateRepository.class);
        Post post = Mockito.mock(Post.class);
        Mockito.when(post.getId()).thenReturn(7L);
        Mockito.when(postRepo.findAll(Mockito.any(Specification.class))).thenReturn(List.of(post));
        Mockito.when(contentRepo.findByPostId(7L)).thenReturn(Optional.of(content));
        Mockito.when(stateRepo.findByContentIdAndStateKey(content.getId(), "progress")).thenReturn(state);
        var body = new ProgressController(postRepo, contentRepo, stateRepo, om).getProgress().getBody();
        return ((List<Map<String, Object>>) body.get("processing")).get(0);
    }

    @Test
    void runtimeStateProgressIsExposedAsCamelCase() throws Exception {
        Content c = new Content();
        c.setId(11L);
        ContentRuntimeState s = Mockito.mock(ContentRuntimeState.class);
        JsonNode v = om.readTree("{\"current_phase\":5,\"last_heartbeat_at\":\"2026-11-25T00:00:00+00:00\",\"updated_at\":\"x\"}");
        Mockito.when(s.getStateValue()).thenReturn(v);
        Map<String, Object> item = firstProcessing(c, Optional.of(s));
        @SuppressWarnings("unchecked")
        Map<String, Object> progress = (Map<String, Object>) item.get("progress");
        assertThat(progress).containsEntry("currentPhase", 5)
            .containsEntry("lastHeartbeatAt", "2026-11-25T00:00:00+00:00")
            .containsKey("updatedAt");
    }

    @Test
    void missingProgressYieldsNullNotError() {
        Content c = new Content();
        c.setId(12L);
        Map<String, Object> item = firstProcessing(c, Optional.empty());
        assertThat(item).containsKey("progress");
        assertThat(item.get("progress")).isNull();
    }
}
