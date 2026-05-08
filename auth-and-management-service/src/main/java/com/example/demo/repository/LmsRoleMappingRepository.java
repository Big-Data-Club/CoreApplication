package com.example.demo.repository;

import com.example.demo.model.LmsRoleMapping;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;

public interface LmsRoleMappingRepository extends JpaRepository<LmsRoleMapping, Long> {

    List<LmsRoleMapping> findByAuthRoleId(Long authRoleId);

    @Query("SELECT m FROM LmsRoleMapping m WHERE m.authRole.name = :roleName")
    List<LmsRoleMapping> findByAuthRoleName(String roleName);

    void deleteByAuthRoleId(Long authRoleId);
}
