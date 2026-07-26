package com.example.demo.repository;

import com.example.demo.model.UserProfileAliasHistory;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Optional;

@Repository
public interface UserProfileAliasHistoryRepository extends JpaRepository<UserProfileAliasHistory, Long> {
    Optional<UserProfileAliasHistory> findFirstByOldAliasOrderByCreatedAtDesc(String oldAlias);
}
