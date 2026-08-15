package com.wagglebot.controller;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.wagglebot.common.JobStatus;
import com.wagglebot.common.JobType;
import com.wagglebot.common.PostStatus;
import com.wagglebot.domain.Content;
import com.wagglebot.domain.ContentRepository;
import com.wagglebot.domain.ContentRuntimeStateRepository;
import com.wagglebot.domain.Post;
import com.wagglebot.domain.PostRepository;
import com.wagglebot.external.ExternalIngestService;
import com.wagglebot.external.ExternalJobRequest;
import com.wagglebot.job.JobService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.nio.file.Path;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 외부 서비스(Again Spring 등)가 사연을 WaggleBot 파이프라인에 밀어넣고 진행 상태를
 * 폴링하기 위한 진입점. 인증은 {@link com.wagglebot.config.ExternalApiKeyFilter}가 처리한다.
 *
 * "jobId"는 별도 Job 큐가 아니라 생성된 Post.id를 그대로 의미한다 — 외부 입장에서는
 * ingest 1건 = post 1건 = 렌더링 1건이므로 postId를 잡 식별자로 노출한다.
 */
@RestController
@RequestMapping("/api/external/jobs")
@RequiredArgsConstructor
@Slf4j
public class ExternalJobController {

    private final ExternalIngestService ingestService;
    private final PostRepository postRepo;
    private final ContentRepository contentRepo;
    private final ContentRuntimeStateRepository runtimeStateRepo;
    private final JobService jobService;
    private final ObjectMapper objectMapper;

    @Value("${app.media-dir:/app/media}")
    private String mediaDirStr;

    @PostMapping
    public ResponseEntity<Map<String, Object>> create(@RequestBody ExternalJobRequest req) {
        ExternalIngestService.IngestResult result = ingestService.ingest(req);
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("ok", true);
        body.put("jobId", result.postId());
        body.put("status", result.status());
        body.put("externalId", req.externalId());
        return ResponseEntity.ok(body);
    }

    @GetMapping("/{jobId}")
    public ResponseEntity<Map<String, Object>> get(@PathVariable Long jobId) {
        Post post = postRepo.findById(jobId)
            .orElseThrow(() -> new IllegalArgumentException("Job not found: " + jobId));
        Content content = contentRepo.findByPostId(jobId).orElse(null);

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("ok", true);
        body.put("jobId", post.getId());
        body.put("status", post.getStatus().name());
        body.put("externalId", post.getOriginId());
        JsonNode progressState = runtimeState(content, "progress");
        body.put("progress", parseProgress(progressState != null ? progressState : content != null ? content.getPipelineState() : null));
        if (content != null && content.getVariantConfig() != null) {
            JsonNode cfg = content.getVariantConfig();
            body.put("priority", cfg.path("priority").asText("NORMAL"));
            if (cfg.hasNonNull("deadline_at")) body.put("deadlineAt", cfg.get("deadline_at").asText());
        }
        if (content != null) {
            JsonNode state = runtimeState(content, "sla");
            if (state == null) state = content.getPipelineState();
            if (state == null) state = objectMapper.getNodeFactory().nullNode();
            body.put("degraded", state.path("degraded").asBoolean(false));
            if (state.has("degrade_reasons")) body.put("degradeReasons", state.get("degrade_reasons"));
            JsonNode diagnostics = runtimeState(content, "generation_diagnostics");
            if (diagnostics != null) body.put("generationDiagnostics", diagnostics);
        }

        if (post.getStatus() == PostStatus.FAILED) addFailure(body, content, post.getLastError());

        boolean rendered = post.getStatus() == PostStatus.PREVIEW_RENDERED || post.getStatus() == PostStatus.RENDERED;
        if (rendered && content != null) {
            body.put("artifacts", buildArtifacts(content));
        }

        if (post.getStatus() == PostStatus.PREVIEW_RENDERED && content != null && isAutoHdRenderEnabled(content)) {
            enqueueHdRenderIfNeeded(post.getId(), body);
        }

        return ResponseEntity.ok(body);
    }

    private JsonNode runtimeState(Content content, String stateKey) {
        if (content == null || content.getId() == null) return null;
        return runtimeStateRepo.findByContentIdAndStateKey(content.getId(), stateKey)
            .map(state -> state.getStateValue())
            .orElse(null);
    }

    private void addFailure(Map<String, Object> body, Content content, String lastError) {
        JsonNode failure = runtimeState(content, "failure");
        String fallback = lastError == null || lastError.isBlank() ? "pipeline failed" : lastError;
        body.put("failureCode", failure == null ? "PIPELINE_UNKNOWN_ERROR" : failure.path("failure_code").asText("PIPELINE_UNKNOWN_ERROR"));
        body.put("failureStage", failure == null ? "unknown" : failure.path("failure_stage").asText("unknown"));
        body.put("retryable", failure == null || failure.path("retryable").asBoolean(true));
        body.put("errorSummary", failure == null ? fallback.substring(0, Math.min(500, fallback.length())) : failure.path("error_summary").asText(fallback));
        JsonNode diagnostics = runtimeState(content, "generation_diagnostics");
        if (diagnostics != null) body.put("generationDiagnostics", diagnostics);
    }

    private Map<String, Object> buildArtifacts(Content content) {
        Map<String, Object> artifacts = new LinkedHashMap<>();
        if (content.getVideoPath() != null) {
            String videoUrl = toMediaUrl(content.getVideoPath());
            artifacts.put("videoUrl", videoUrl);
            artifacts.put("mp4Url", videoUrl); // ASM / Again Spring alias
        }
        if (content.getAudioPath() != null) artifacts.put("audioUrl", toMediaUrl(content.getAudioPath()));
        // Intro/cover thumbnail for Shorts (upload_meta.thumbnail_path from ai_worker).
        JsonNode uploadMeta = content.getUploadMeta();
        if (uploadMeta != null && uploadMeta.hasNonNull("thumbnail_path")) {
            String thumbPath = uploadMeta.get("thumbnail_path").asText("").trim();
            if (!thumbPath.isEmpty()) {
                java.nio.file.Path thumbFile = java.nio.file.Path.of(thumbPath);
                if (java.nio.file.Files.isRegularFile(thumbFile)) {
                    String thumbUrl = toMediaUrl(thumbPath);
                    artifacts.put("thumbnailUrl", thumbUrl);
                    artifacts.put("thumbUrl", thumbUrl);
                }
            }
        }
        return artifacts;
    }

    /** GalleryController.hdRender()와 동일한 활성 잡 조회로 중복 큐잉을 막는다. */
    private void enqueueHdRenderIfNeeded(Long postId, Map<String, Object> body) {
        var activeStatuses = List.of(JobStatus.PENDING, JobStatus.RUNNING);
        var existingJob = jobService.findActiveJob(JobType.HD_RENDER, postId, activeStatuses);
        if (existingJob.isPresent()) {
            body.put("hdRenderJobId", existingJob.get().getId());
            return;
        }
        var job = jobService.createJob(JobType.HD_RENDER, postId, null);
        body.put("hdRenderJobId", job.getId());
        log.info("[external] PREVIEW_RENDERED + auto_hd_render → HD_RENDER 큐잉: postId={} jobId={}", postId, job.getId());
    }

    private boolean isAutoHdRenderEnabled(Content content) {
        JsonNode cfg = content.getVariantConfig();
        return cfg != null && cfg.path("auto_hd_render").asBoolean(false);
    }

    /** ProgressController.parseProgress()와 동일한 snake_case→camelCase 변환(TS 타입 일관성). */
    private Map<String, Object> parseProgress(JsonNode pipelineState) {
        if (pipelineState == null) return null;
        JsonNode progressNode = pipelineState.get("progress");
        if (progressNode == null || progressNode.isNull()) return null;
        Map<String, Object> raw = objectMapper.convertValue(progressNode, new TypeReference<Map<String, Object>>() {});
        Map<String, Object> out = new LinkedHashMap<>();
        raw.forEach((k, v) -> out.put(snakeToCamel(k), v));
        return out;
    }

    private static String snakeToCamel(String s) {
        int idx = s.indexOf('_');
        if (idx < 0) return s;
        StringBuilder sb = new StringBuilder(s.length());
        boolean up = false;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '_') { up = true; }
            else { sb.append(up ? Character.toUpperCase(c) : c); up = false; }
        }
        return sb.toString();
    }

    private String toMediaUrl(String absolutePath) {
        Path mediaDir = Path.of(mediaDirStr);
        Path file = Path.of(absolutePath);
        Path rel = file.startsWith(mediaDir) ? mediaDir.relativize(file) : file.getFileName();
        return "/api/media/" + rel.toString().replace('\\', '/');
    }
}
