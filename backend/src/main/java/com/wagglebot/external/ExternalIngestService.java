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

    private static final String OUTRO_PAIRED = "상대방의 사연이 궁금하면 댓글을 확인해주세요";
    private static final String OUTRO_SOLO = "여러분의 의견을 댓글로 남겨주세요";

    private final PostRepository postRepo;
    private final CommentRepository commentRepo;
    private final ContentRepository contentRepo;
    private final ObjectMapper objectMapper;

    public record IngestResult(Long postId, String status) {}

    @Transactional
    public IngestResult ingest(ExternalJobRequest req) {
        validate(req);

        String siteCode = req.source();
        String originId = req.externalId();

        Optional<Post> existing = postRepo.findBySiteCodeAndOriginId(siteCode, originId);
        if (existing.isPresent() && existing.get().getStatus() != PostStatus.FAILED) {
            Post post = existing.get();
            log.info(
                "[external] 중복 ingest — 기존 잡 반환: site={} originId={} postId={} status={}",
                siteCode, originId, post.getId(), post.getStatus()
            );
            return new IngestResult(post.getId(), post.getStatus().name());
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
            post.setTitle(req.title());
            post.setContent(req.body());
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
            post.setTitle(req.title());
            post.setContent(req.body());
            post.setStatus(PostStatus.APPROVED);
            post.setEngagementScore(0.0);
            post.setRetryCount(0);
            post.setCreatedAt(now);
            post.setUpdatedAt(now);
            post = postRepo.save(post);
        }

        upsertComments(post.getId(), req.comments());
        upsertContent(post.getId(), now, req, videoGen, paired, outroText, autoHdRender);

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
        boolean videoGen, boolean paired, String outroText, boolean autoHdRender
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
