package com.wagglebot.domain;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface ContentRuntimeStateRepository extends JpaRepository<ContentRuntimeState, ContentRuntimeStateId> {
    Optional<ContentRuntimeState> findByContentIdAndStateKey(Long contentId, String stateKey);
}
