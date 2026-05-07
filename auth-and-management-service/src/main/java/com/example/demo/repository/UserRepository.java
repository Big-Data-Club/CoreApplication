package com.example.demo.repository;

import com.example.demo.model.User;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import java.util.Collection;
import java.util.List;
import java.util.Optional;
import java.util.Set;

@Repository
public interface UserRepository extends JpaRepository<User, Long> {
    Optional<User> findByEmail(String email);
    boolean existsByEmail(String email);
    boolean existsByCode(String code);

    Optional<User> findByGoogleId(String googleId);

    List<User> findByPendingApprovalTrue();

    /**
     * Batch lookup: returns the codes from the input set that already exist in the DB.
     */
    @org.springframework.data.jpa.repository.Query("SELECT u.code FROM User u WHERE u.code IN :codes")
    Set<String> findExistingCodes(@org.springframework.data.repository.query.Param("codes") Collection<String> codes);

    /**
     * Batch lookup: returns the emails from the input set that already exist in the DB.
     */
    @org.springframework.data.jpa.repository.Query("SELECT u.email FROM User u WHERE u.email IN :emails")
    Set<String> findExistingEmails(@org.springframework.data.repository.query.Param("emails") Collection<String> emails);
}
