package com.wagglebot.domain;

import java.io.Serializable;
import java.util.Objects;

public final class ContentRuntimeStateId implements Serializable {
    private Long contentId;
    private String stateKey;

    public ContentRuntimeStateId() {}
    public ContentRuntimeStateId(Long contentId, String stateKey) {
        this.contentId = contentId;
        this.stateKey = stateKey;
    }
    @Override public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof ContentRuntimeStateId that)) return false;
        return Objects.equals(contentId, that.contentId) && Objects.equals(stateKey, that.stateKey);
    }
    @Override public int hashCode() { return Objects.hash(contentId, stateKey); }
}
