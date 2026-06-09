package com.wagglebot.common;

/** Python PostStatus enum 값과 바이트 동일 — @Enumerated(EnumType.STRING) 사용. */
public enum PostStatus {
    COLLECTED, EDITING, APPROVED, PROCESSING,
    PREVIEW_RENDERED, RENDERED, UPLOADED, DECLINED, FAILED
}
