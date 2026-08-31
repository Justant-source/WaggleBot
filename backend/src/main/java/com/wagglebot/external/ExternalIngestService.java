package com.wagglebot.external;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.wagglebot.common.PostStatus;
import com.wagglebot.domain.Comment;
import com.wagglebot.domain.CommentRepository;
import com.wagglebot.domain.Content;
import com.wagglebot.domain.ContentRepository;
import com.wagglebot.domain.Post;
import com.wagglebot.domain.PostRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;

/**
 * 외부 서비스(Again Spring 등) 사연을 Post/Comment/Content로 적재한다.
 *
 * 멱등성: (site_code=source, origin_id=externalId) 유니크 키(uq_site_origin) 기준.
 * 기존 Post가 있고 상태가 FAILED가 아니면 재적재 없이 그대로 반환한다.
 * FAILED면 재시도로 간주해 내용을 갱신하고 APPROVED로 되돌린다.
 */
@Service
@RequiredArgsConstructor
@Slf4j
public class ExternalIngestService {

    private static final String OUTRO_PAIRED = "상대방의 사연도 궁금하시죠? 댓글에서 확인해 보세요.";
    private static final String OUTRO_SOLO = "여러분은 어떻게 생각하세요? 댓글로 알려주세요.";

    private final PostRepository postRepo;
    private final CommentRepository commentRepo;
    private final ContentRepository contentRepo;
    private final ObjectMapper objectMapper;

    public record IngestResult(Long postId, String status) {}

    @Transactional
    public IngestResult ingest(ExternalJobRequest req) {
        validate(req);

        // Defense-in-depth normalization (2026-08-16) — ASM's StoryBrief validators already
        // normalize this text before it reaches here in the normal AS → ASM → WaggleBot path;
        // this catches any other caller of this endpoint the same way.
        String normalizedTitle = ExternalTextNormalizer.normalize(req.title());
        String normalizedBody = ExternalTextNormalizer.normalize(req.body());

        String siteCode = req.source();
        String originId = req.externalId();

        Optional<Post> existing = postRepo.findBySiteCodeAndOriginId(siteCode, originId);
        String requestedVoice = (req.options() != null && req.options().ttsVoice() != null)
            ? req.options().ttsVoice().trim() : "";
        if (existing.isPresent() && existing.get().getStatus() != PostStatus.FAILED) {
            Post post = existing.get();
            String storedVoice = contentRepo.findByPostId(post.getId())
                .map(Content::getTtsVoice)
                .orElse(null);
            boolean voiceChanged = requestedVoice != null && !requestedVoice.isBlank()
                && (storedVoice == null || !requestedVoice.equals(storedVoice.trim()));
            if (!voiceChanged) {
                log.info(
                    "[external] 중복 ingest — 기존 잡 반환: site={} originId={} postId={} status={}",
                    siteCode, originId, post.getId(), post.getStatus()
                );
                return new IngestResult(post.getId(), post.getStatus().name());
            }
            // TTS voice changed — force re-pipeline with updated content.
            post.setStatus(PostStatus.FAILED);
            post.setUpdatedAt(LocalDateTime.now());
            postRepo.save(post);
            log.info(
                "[external] TTS voice changed ({} -> {}) — force re-ingest postId={}",
                storedVoice, requestedVoice, post.getId()
            );
        }

        boolean paired = Boolean.TRUE.equals(req.paired());
        var options = req.options();
        boolean videoGen = options != null && Boolean.TRUE.equals(options.videoGen());
        boolean autoHdRender = options == null || options.autoHdRender() == null || options.autoHdRender();
        String outroText = paired ? OUTRO_PAIRED : OUTRO_SOLO;

        LocalDateTime now = LocalDateTime.now();
        Post post;
        if (existing.isPresent()) {
            // FAILED 재시도 — 기존 Post를 되살려 재처리 큐로 되돌린다.
            post = existing.get();
            post.setTitle(normalizedTitle);
            post.setContent(normalizedBody);
            post.setStatus(PostStatus.APPROVED);
            post.setRetryCount((post.getRetryCount() == null ? 0 : post.getRetryCount()) + 1);
            post.setLastError(null);
            post.setUpdatedAt(now);
            post = postRepo.save(post);
            log.info(
                "[external] FAILED 게시글 재수집: postId={} site={} originId={}",
                post.getId(), siteCode, originId
            );
        } else {
            post = new Post();
            post.setSiteCode(siteCode);
            post.setOriginId(originId);
            post.setTitle(normalizedTitle);
            post.setContent(normalizedBody);
            post.setStatus(PostStatus.APPROVED);
            post.setEngagementScore(0.0);
            post.setRetryCount(0);
            post.setCreatedAt(now);
            post.setUpdatedAt(now);
            post = postRepo.save(post);
        }

        upsertComments(post.getId(), req.comments());
        String ttsVoice = (options != null && options.ttsVoice() != null) ? options.ttsVoice().trim() : null;
        String commentVoices = (options != null && options.commentVoices() != null) ? options.commentVoices().trim() : null;
        String mood = (options != null && options.mood() != null) ? options.mood().trim() : null;
        String ttsEmotion = (options != null && options.ttsEmotion() != null) ? options.ttsEmotion().trim() : null;
        Integer maxDurationSec = options != null ? options.maxDurationSec() : null;
        String platformLayout = (options != null && options.platformLayout() != null)
            ? options.platformLayout().trim() : null;
        // Video path uses sibom_plan only — metaphorId is intentionally ignored (unplugged).
        var sibomPlan = (options != null) ? options.sibomPlan() : null;
        boolean marketingCritical = "again_spring".equals(siteCode) || (options != null && "MARKETING_CRITICAL".equalsIgnoreCase(options.priority()));
        boolean preScripted = options != null && Boolean.TRUE.equals(options.preScripted());
        String renderProfile = (options != null && options.renderProfile() != null) ? options.renderProfile().trim() : null;
        String bgmTrack = (options != null && options.bgmTrack() != null) ? options.bgmTrack().trim() : null;
        OffsetDateTime deadlineAt = options != null ? options.deadlineAt() : null;
        if (marketingCritical && deadlineAt == null) deadlineAt = OffsetDateTime.now(ZoneOffset.UTC).plusMinutes(10);
        upsertContent(
            post.getId(), now, req, videoGen, paired, outroText, autoHdRender,
            ttsVoice, commentVoices, mood, ttsEmotion, maxDurationSec, platformLayout, sibomPlan,
            marketingCritical, preScripted, renderProfile, deadlineAt, bgmTrack
        );

        log.info(
            "[external] ingest 완료: site={} originId={} postId={} paired={} videoGen={} autoHdRender={}",
            siteCode, originId, post.getId(), paired, videoGen, autoHdRender
        );
        return new IngestResult(post.getId(), post.getStatus().name());
    }

    private void validate(ExternalJobRequest req) {
        if (req == null) throw new IllegalArgumentException("request body is required");
        if (isBlank(req.source())) throw new IllegalArgumentException("source is required");
        if (isBlank(req.externalId())) throw new IllegalArgumentException("externalId is required");
        if (isBlank(req.title())) throw new IllegalArgumentException("title is required");
        if (req.body() == null) throw new IllegalArgumentException("body is required");
    }

    private void upsertComments(Long postId, List<ExternalJobRequest.CommentInput> comments) {
        if (comments == null || comments.isEmpty()) return;
        for (ExternalJobRequest.CommentInput c : comments) {
            if (c == null || isBlank(c.author()) || c.body() == null) continue;
            String hash = sha256(c.author() + ":" + c.body());
            if (commentRepo.existsByPostIdAndAuthorAndContentHash(postId, c.author(), hash)) {
                continue; // 재시도 시 동일 댓글 중복 삽입 방지 (uq_post_comment)
            }
            Comment comment = new Comment();
            comment.setPostId(postId);
            comment.setAuthor(c.author());
            comment.setContent(c.body());
            comment.setContentHash(hash);
            comment.setLikes(c.likeCount() != null ? c.likeCount() : 0);
            commentRepo.save(comment);
        }
    }

    private void upsertContent(
        Long postId, LocalDateTime now, ExternalJobRequest req,
        boolean videoGen, boolean paired, String outroText, boolean autoHdRender,
        String ttsVoice,
        String commentVoices,
        String mood,
        String ttsEmotion,
        Integer maxDurationSec,
        String platformLayout,
        com.fasterxml.jackson.databind.JsonNode sibomPlan,
        boolean marketingCritical, boolean preScripted, String renderProfile, OffsetDateTime deadlineAt,
        String bgmTrack
    ) {
        Content content = contentRepo.findByPostId(postId).orElseGet(() -> {
            Content c = new Content();
            c.setPostId(postId);
            c.setCreatedAt(now);
            return c;
        });

        ObjectNode variantConfig = objectMapper.createObjectNode();
        variantConfig.put("source", req.source());
        variantConfig.put("external_id", req.externalId());
        variantConfig.put("video_gen", videoGen);
        variantConfig.put("paired", paired);
        variantConfig.put("outro_text", outroText);
        variantConfig.put("auto_hd_render", autoHdRender);
        variantConfig.put("priority", marketingCritical ? "MARKETING_CRITICAL" : "NORMAL");
        variantConfig.put("pre_scripted", preScripted);
        if (renderProfile != null && !renderProfile.isBlank()) variantConfig.put("render_profile", renderProfile);
        if (deadlineAt != null) variantConfig.put("deadline_at", deadlineAt.toString());
        // 관리자가 고른 BGM. 비어 있으면 director 가 hook_emotion 으로 자동 선택한다.
        if (bgmTrack != null && !bgmTrack.isBlank()) variantConfig.put("bgm_track", bgmTrack);
        if (ttsVoice != null && !ttsVoice.isBlank()) {
            variantConfig.put("tts_voice", ttsVoice);
            content.setTtsVoice(ttsVoice);
        }
        // metaphor_id intentionally omitted — video path is sibom_plan only (cream+text if empty).
        if (commentVoices != null && !commentVoices.isBlank()) {
            // JSON array string preferred; comma-separated also accepted by Python resolver
            variantConfig.put("comment_voices", commentVoices);
        }
        if (mood != null && !mood.isBlank()) {
            variantConfig.put("mood", mood);
        }
        if (ttsEmotion != null && !ttsEmotion.isBlank()) {
            variantConfig.put("tts_emotion", ttsEmotion);
        }
        if (maxDurationSec != null && maxDurationSec > 0) {
            variantConfig.put("max_duration_sec", maxDurationSec);
        }
        if (platformLayout != null && !platformLayout.isBlank()) {
            variantConfig.put("platform_layout", platformLayout);
        }
        if (sibomPlan != null && sibomPlan.isArray()) {
            variantConfig.set("sibom_plan", sibomPlan);
        }
        content.setVariantConfig(variantConfig);

        contentRepo.save(content);
    }

    /** crawlers/base.py의 댓글 해시 규칙(sha256(author:content)[:32])과 동일 — 두 경로가 같은 uq_post_comment 키 사용. */
    private static String sha256(String input) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hashBytes = digest.digest(input.getBytes(StandardCharsets.UTF_8));
            StringBuilder sb = new StringBuilder();
            for (byte b : hashBytes) sb.append(String.format("%02x", b));
            return sb.substring(0, 32);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }

    private static boolean isBlank(String s) {
        return s == null || s.isBlank();
    }
}
