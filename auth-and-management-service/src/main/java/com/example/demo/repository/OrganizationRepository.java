package com.example.demo.repository;

import com.example.demo.model.Organization;
import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface OrganizationRepository extends JpaRepository<Organization, Long> {
    @org.springframework.data.jpa.repository.Lock(jakarta.persistence.LockModeType.PESSIMISTIC_WRITE)
    @org.springframework.data.jpa.repository.Query("select o from Organization o where o.id = :id")
    Optional<Organization> lockForSiteUpdate(@org.springframework.data.repository.query.Param("id") Long id);
    Optional<Organization> findBySlug(String slug);
    Optional<Organization> findByName(String name);
    boolean existsBySlug(String slug);
}
